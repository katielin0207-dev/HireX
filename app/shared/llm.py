"""共享 LLM 调用入口。

对项目已有的 LLMClient 做薄封装：
- 单例，避免每次新建 httpx.Client
- 默认 temperature=0.3（评分类任务要稳定）
- 自带重试 + JSON 修复（LLMClient 内置）

用法：
    from app.shared import call_llm

    # JSON 输出（推荐，结构化结果都用这个）
    result = call_llm(
        "分析这份简历...",
        system="你是资深技术面试官，只输出 JSON。",
        expect_json=True,
    )

    # 文本输出（写总结、写纪要时用）
    text = call_llm("把以下要点整理成一段话...", expect_json=False)

注意：
- expect_json=True 时返回 dict/list；失败会抛 LLMError，调用方自己 try
- 批量场景不要 for 循环串行调，用 app.shared.parallel.map_llm 并发
"""
import threading
from typing import Any

from ..llm_client import LLMClient

_client = None
_lock = threading.Lock()


def _get_client() -> LLMClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = LLMClient()
    return _client


def call_llm(
    user_prompt: str,
    system: str = "",
    expect_json: bool = True,
    temperature: float = 0.3,
    max_retries: int = 3,
) -> Any:
    """统一的 LLM 调用入口。参数语义见模块 docstring。"""
    return _get_client().chat(
        user_prompt=user_prompt,
        system_prompt=system,
        expect_json=expect_json,
        temperature=temperature,
        max_retries=max_retries,
    )
