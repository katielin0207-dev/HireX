"""
试题生成引擎：生成多维度面试题 + 模糊点追问。

核心功能：
1. 基于JD+简历+匹配分析，生成至少12道面试题（5个维度）
2. 针对简历模糊点，生成3-5个递进式追问
3. 每题含考察点、难度、评分标准、追问

维度覆盖：
- 技术基础题：考察岗位必备技能
- 项目深挖题：追问简历项目的技术细节
- 场景设计题：模拟真实工作场景
- 行为面试题：考察软技能
- 模糊点追问题：针对简历模糊处追问
"""
import json
from typing import Any
from .llm_client import llm_client, LLMError
from .prompts import (
    SYSTEM_PROMPT,
    QUESTION_GEN_PROMPT,
    AMBIGUITY_FOLLOWUP_PROMPT,
)


class QuestionGenError(Exception):
    pass


def build_revision_directive(feedback) -> str:
    """把 Checker 的结构化 issues 变成给 Agent 的修订指令。

    ★ 这是修订闭环真正起作用的地方。之前 Checker 生成了 issues（含
      suggested_fix），但没有任何代码把它送回 Agent —— 反馈结构再规范，
      不送回去就只是一份报告。

    刻意做的两件事：
      · 按 severity 排序，critical 在前 —— 模型对靠前的指令服从度更高
      · 逐条带上 location，让"改哪儿"是明确的，而不是"整体重写一遍"
    """
    if not feedback:
        return ""

    issues = getattr(feedback, "issues", None) or []
    if not issues:
        return ""

    order = {"critical": 0, "major": 1, "minor": 2}
    def sev(i):
        s = getattr(i, "severity", None)
        return getattr(s, "value", str(s or "minor"))

    ranked = sorted(issues, key=lambda i: order.get(sev(i), 3))

    lines = [
        "",
        "════════════════════════════════════════════════",
        "⚠️ 上一版输出未通过校验，请**针对性修订**后重新输出完整结果。",
        "",
        "校准得分：" + "、".join(
            f"{k} {v}" for k, v in (getattr(feedback, "calibration_scores", {}) or {}).items()
        ),
        "",
        "必须修正的问题（按严重程度排序）：",
    ]
    for n, issue in enumerate(ranked, 1):
        lines.append(
            f"{n}. [{sev(issue)}] {getattr(issue, 'dimension', '')} @ {getattr(issue, 'location', '')}\n"
            f"   问题：{getattr(issue, 'description', '')}\n"
            f"   要求：{getattr(issue, 'suggested_fix', '')}"
        )
    lines += [
        "",
        "★ 只修上述问题，不要改动已经通过校验的部分。",
        "★ 输出仍须是完整的 JSON，不是差异片段。",
        "════════════════════════════════════════════════",
        "",
    ]
    return "\n".join(lines)


def generate_questions(
    jd_data: dict,
    resume_data: dict,
    match_result: dict,
    revision_feedback=None,
    temperature: float = None,
) -> dict:
    """
    生成多维度面试题。

    Args:
        jd_data: 结构化的 JD 数据
        resume_data: 结构化的简历数据
        match_result: 匹配度评分结果
        revision_feedback: ★ Checker 的 CheckerResult。非空时进入【修订模式】，
                           把 issues + suggested_fix 拼进 prompt 让模型定点改
        temperature: 由 Harness 降级链传下来的温度

    Returns:
        {
            "questions": [...],       # 面试题列表
            "category_stats": {...},  # 各维度题量统计
            "difficulty_stats": {...} # 难度分布统计
        }
    """
    jd_json = json.dumps(jd_data, ensure_ascii=False, indent=2)
    resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)
    match_analysis = json.dumps(match_result, ensure_ascii=False, indent=2)

    prompt = QUESTION_GEN_PROMPT.format(
        jd_json=jd_json,
        resume_json=resume_json,
        match_analysis=match_analysis,
    ) + build_revision_directive(revision_feedback)

    chat_kwargs = {"user_prompt": prompt, "system_prompt": SYSTEM_PROMPT, "expect_json": True}
    if temperature is not None:
        chat_kwargs["temperature"] = temperature

    result = llm_client.chat(**chat_kwargs)

    if not isinstance(result, dict) or "questions" not in result:
        raise QuestionGenError("面试题生成结果格式异常")

    questions = result["questions"]

    # 统计各维度题量
    category_stats = {}
    difficulty_stats = {}
    for q in questions:
        cat = q.get("category", "未知")
        diff = q.get("difficulty", "未知")
        category_stats[cat] = category_stats.get(cat, 0) + 1
        difficulty_stats[diff] = difficulty_stats.get(diff, 0) + 1

    return {
        "questions": questions,
        "category_stats": category_stats,
        "difficulty_stats": difficulty_stats,
        "total_count": len(questions),
    }


def generate_ambiguity_followups(resume_data: dict) -> dict:
    """
    针对简历中的模糊点，生成递进式追问。

    Returns:
        {
            "followup_groups": [
                {
                    "ambiguous_point": "...",
                    "severity": "high/medium/low",
                    "followups": [
                        {
                            "order": 1,
                            "question": "...",
                            "intent": "...",
                            "expected_answer": "...",
                            "red_flag": "..."
                        }
                    ]
                }
            ],
            "total_followups": int
        }
    """
    # 从简历中提取模糊点
    ambiguous_points = resume_data.get("ambiguous_points", [])

    # 如果简历解析没有识别到模糊点，返回空结果
    if not ambiguous_points:
        return {
            "followup_groups": [],
            "total_followups": 0,
            "note": "简历中未识别到明显模糊点",
        }

    resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)
    ambiguous_str = json.dumps(ambiguous_points, ensure_ascii=False, indent=2)

    prompt = AMBIGUITY_FOLLOWUP_PROMPT.format(
        resume_json=resume_json,
        ambiguous_points=ambiguous_str,
    )

    result = llm_client.chat(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        expect_json=True,
    )

    if not isinstance(result, dict) or "followup_groups" not in result:
        raise QuestionGenError("模糊点追问生成结果格式异常")

    # 统计追问总数
    total = sum(len(g.get("followups", [])) for g in result["followup_groups"])

    return {
        "followup_groups": result["followup_groups"],
        "total_followups": total,
    }


def run_question_pipeline(
    jd_data: dict,
    resume_data: dict,
    match_result: dict,
) -> dict:
    """
    完整的试题生成流程：面试题生成 + 模糊点追问生成。
    """
    try:
        # Step 1: 生成多维度面试题
        questions_result = generate_questions(jd_data, resume_data, match_result)

        # Step 2: 生成模糊点追问
        followups_result = generate_ambiguity_followups(resume_data)

        return {
            "success": True,
            "questions": questions_result,
            "ambiguity_followups": followups_result,
        }
    except LLMError as e:
        return {"success": False, "error": f"LLM 调用失败: {str(e)}"}
    except QuestionGenError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"试题生成流程异常: {str(e)}"}
