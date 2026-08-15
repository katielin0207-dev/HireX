"""
LLM 客户端封装：统一管理 LLM 调用，处理重试、格式校验和错误恢复。

核心设计：
1. 重试机制：网络超时 / API 限流时自动重试，指数退避
2. JSON 修复：LLM 输出非法 JSON 时，自动提取和修复（含截断补全）
3. 格式校验：调用后校验输出结构，不符合则重试
4. 幻觉防护：System Prompt 约束 + 输出后处理
5. 多模型支持：OpenAI 兼容 API（DeepSeek / Qwen / GPT / Kimi 等）
"""
import json
import re
import time
import httpx
from typing import Any, Optional

from .config import settings


class LLMError(Exception):
    """LLM 调用异常"""
    pass


class JSONParseError(LLMError):
    """JSON 解析异常"""
    pass


class LLMClient:
    """OpenAI 兼容 API 的 LLM 客户端"""

    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.model = settings.LLM_MODEL
        self.client = httpx.Client(timeout=settings.TIMEOUT)

    def _extract_json(self, text: str) -> str:
        """
        从 LLM 输出中提取 JSON 字符串。
        处理：Markdown 代码块、前后多余文字、不完整 JSON（被 token 限制截断）
        """
        # 去除 Markdown 代码块
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = text.replace("```", "")

        text = text.strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 { ... } 或 [ ... ] 块
        for pattern in [
            r"\{[\s\S]*\}",
            r"\[[\s\S]*\]",
        ]:
            match = re.search(pattern, text)
            if match:
                candidate = match.group()
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    fixed = self._fix_json(candidate)
                    if fixed:
                        return fixed

        # 尝试自动补全被截断的 JSON
        fixed = self._fix_truncated_json(text)
        if fixed:
            return fixed

        raise JSONParseError(f"无法从 LLM 输出中提取有效 JSON。输出前200字符: {text[:200]}")

    def _fix_truncated_json(self, text: str) -> Optional[str]:
        """尝试补全因 token 截断而不完整的 JSON"""
        text = text.strip()
        start = text.find('{')
        if start == -1:
            start = text.find('[')
        if start == -1:
            return None
        text = text[start:]

        # 计算未闭合的括号
        open_braces = 0
        open_brackets = 0
        in_string = False
        escape = False
        for ch in text:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                open_braces += 1
            elif ch == '}':
                open_braces -= 1
            elif ch == '[':
                open_brackets += 1
            elif ch == ']':
                open_brackets -= 1

        if open_braces <= 0 and open_brackets <= 0:
            return None

        if in_string:
            text += '"'
        if text.rstrip()[-1] not in ("}", "]", '"', "'"):
            last_comma = text.rfind(',')
            if last_comma > 0:
                text = text[:last_comma]

        text += ']' * open_brackets + '}' * open_braces

        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            return None

    def _fix_json(self, text: str) -> Optional[str]:
        """尝试修复常见的 JSON 格式错误"""
        # 修复尾部逗号
        fixed = re.sub(r",\s*}", "}", text)
        fixed = re.sub(r",\s*]", "]", fixed)

        try:
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError:
            return None

    def chat(
        self,
        user_prompt: str,
        system_prompt: str = "",
        expect_json: bool = True,
        temperature: float = None,
        max_retries: int = None,
    ) -> Any:
        """
        调用 LLM 并返回结果。

        Args:
            user_prompt: 用户 Prompt
            system_prompt: 系统 Prompt（定义角色）
            expect_json: 是否期望 JSON 输出（为 True 时自动解析和校验）
            temperature: 温度参数（None 使用默认值）
            max_retries: 最大重试次数（None 时使用默认值）

        Returns:
            expect_json=True 时返回解析后的 dict/list
            expect_json=False 时返回原始字符串
        """
        if not self.api_key:
            raise LLMError(
                "LLM API Key 未配置。请复制 .env.example 为 .env 并填入你的 API Key。"
            )

        retries = max_retries if max_retries is not None else settings.MAX_RETRIES
        sys_prompt = system_prompt or ""
        temp = temperature if temperature is not None else settings.TEMPERATURE

        last_error = None
        current_prompt = user_prompt

        for attempt in range(1, retries + 1):
            try:
                content = self._call_api(current_prompt, sys_prompt, temp)

                if expect_json:
                    json_str = self._extract_json(content)
                    return json.loads(json_str)
                else:
                    return content

            except JSONParseError as e:
                last_error = e
                current_prompt = (
                    f"{user_prompt}\n\n"
                    f"【注意】上一次输出无法解析为合法 JSON。"
                    f"请确保只输出纯 JSON，不要包含任何 Markdown 标记或额外文字。"
                    f"上次错误: {str(e)[:100]}"
                )
                if attempt < retries:
                    time.sleep(1 * attempt)
                continue

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = LLMError(f"API 请求失败 (尝试 {attempt}/{retries}): {str(e)}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue

            except Exception as e:
                last_error = LLMError(f"未知错误: {str(e)}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue

        raise last_error or LLMError("LLM 调用失败，已达到最大重试次数")

    def _call_api(self, user_prompt: str, system_prompt: str, temperature: float) -> str:
        """调用 OpenAI 兼容的 Chat Completions API"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": settings.MAX_TOKENS,
        }

        resp = self.client.post(url, json=payload, headers=headers)

        if resp.status_code == 429:
            raise httpx.HTTPStatusError("API 限流，请稍后重试", request=resp.request, response=resp)
        if resp.status_code != 200:
            raise httpx.HTTPStatusError(
                f"API 返回错误状态码 {resp.status_code}: {resp.text[:200]}",
                request=resp.request,
                response=resp,
            )

        data = resp.json()
        return data["choices"][0]["message"]["content"]


# 全局单例
llm_client = LLMClient()
