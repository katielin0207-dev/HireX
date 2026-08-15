"""
匹配度评分引擎：解析 JD 和简历，计算匹配度评分，给出精准匹配理由。

处理流程：
1. 解析 JD → 结构化提取岗位要求
2. 解析简历 → 结构化提取候选人信息 + 识别模糊点
3. 匹配评分 → 多维度打分 + 是否推进建议
"""
import json
from typing import Any
from .llm_client import llm_client, LLMError
from .prompts import (
    SYSTEM_PROMPT,
    JD_PARSE_PROMPT,
    RESUME_PARSE_PROMPT,
    MATCH_SCORE_PROMPT,
)


class MatchError(Exception):
    pass


def parse_jd(jd_text: str) -> dict:
    """解析 JD 文本，返回结构化的岗位要求"""
    prompt = JD_PARSE_PROMPT.format(jd_text=jd_text)
    result = llm_client.chat(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        expect_json=True,
    )
    if not isinstance(result, dict):
        raise MatchError("JD 解析结果格式异常")
    return result


def parse_resume(resume_text: str) -> dict:
    """解析简历文本，返回结构化的候选人信息（含模糊点识别）"""
    prompt = RESUME_PARSE_PROMPT.format(resume_text=resume_text)
    result = llm_client.chat(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        expect_json=True,
    )
    if not isinstance(result, dict):
        raise MatchError("简历解析结果格式异常")
    return result


def calculate_match(
    jd_data: dict,
    resume_data: dict,
    revision_feedback=None,
    temperature: float = None,
) -> dict:
    """
    计算匹配度评分。

    Args:
        revision_feedback: ★ Checker 的 CheckerResult。非空 → 进入修订模式，
                           把 issues + suggested_fix 拼进 prompt 定点改。
        temperature: 由 Harness 降级链传下来的温度。

    返回结构：
    {
        "overall_score": int,
        "score_breakdown": { 技能/经验/学历/项目 各维度评分 },
        "matched_points": [...],
        "gap_points": [...],
        "risk_points": [...],
        "recommendation": "推进 / 待定 / 不推进",
        "recommendation_reason": "..."
    }
    """
    from .question_generator import build_revision_directive

    jd_json = json.dumps(jd_data, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)

    prompt = MATCH_SCORE_PROMPT.format(
        jd_json=jd_json, resume_json=resume_json
    ) + build_revision_directive(revision_feedback)

    chat_kwargs = {"user_prompt": prompt, "system_prompt": SYSTEM_PROMPT, "expect_json": True}
    if temperature is not None:
        chat_kwargs["temperature"] = temperature

    result = llm_client.chat(**chat_kwargs)

    if not isinstance(result, dict) or "overall_score" not in result:
        raise MatchError("匹配度评分结果格式异常")

    return result


def run_match_pipeline(jd_text: str, resume_text: str) -> dict:
    """
    完整的匹配评分流程：JD解析 → 简历解析 → 匹配评分

    返回所有中间结果，供前端展示和后续试题生成使用。
    """
    try:
        # Step 1: 解析 JD
        jd_data = parse_jd(jd_text)

        # Step 2: 解析简历（含模糊点识别）
        resume_data = parse_resume(resume_text)

        # Step 3: 匹配评分
        match_result = calculate_match(jd_data, resume_data)

        return {
            "success": True,
            "jd_data": jd_data,
            "resume_data": resume_data,
            "match_result": match_result,
        }
    except LLMError as e:
        return {"success": False, "error": f"LLM 调用失败: {str(e)}"}
    except MatchError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"匹配评分流程异常: {str(e)}"}
