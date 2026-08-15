"""
评估报告生成器：基于完整面试记录，生成结构化评估报告。
"""
import json
from typing import Any

from .config import settings
from .llm_client import llm_client
from .prompts import REPORT_PROMPT


class ReportError(Exception):
    """报告生成异常"""
    pass


def generate_report(interview_data: dict) -> dict:
    """
    生成面试评估报告。

    Args:
        interview_data: 面试数据，包含 jd_data, resume_data, persona, turns 等

    Returns:
        结构化报告 dict
    """
    jd_data = interview_data.get("jd_data", {})
    resume_data = interview_data.get("resume_data", {})
    persona = interview_data.get("persona", {})
    turns = interview_data.get("turns", [])

    # 构建对话记录文本
    transcript_parts = []
    for t in turns:
        transcript_parts.append(f"--- 第{t.get('round', '?')}轮 ---")
        transcript_parts.append(f"Q: {t.get('question', '')}")
        transcript_parts.append(f"A: {t.get('answer', '')}")
        if t.get("evaluation"):
            ev = t["evaluation"]
            transcript_parts.append(f"[评分: {ev.get('score', '?')}, 质量: {ev.get('answer_quality', '?')}]")
        transcript_parts.append("")

    result = llm_client.chat(
        user_prompt=REPORT_PROMPT.format(
            candidate_name=resume_data.get("name", "候选人"),
            position=jd_data.get("title", "未知岗位"),
            interviewer_name=persona.get("persona_name", "面试官"),
            total_rounds=len(turns),
            interview_transcript="\n".join(transcript_parts),
            jd_requirements=json.dumps(jd_data, ensure_ascii=False, indent=2),
            resume_summary=json.dumps(resume_data, ensure_ascii=False, indent=2),
        ),
        expect_json=True,
        temperature=settings.EVAL_TEMPERATURE,
    )

    # 计算加权总分
    dim_scores = result.get("dimension_scores", {})
    weighted_total = 0
    for key, dim in dim_scores.items():
        score = dim.get("score", 0)
        weight = dim.get("weight", 20)
        weighted_total += score * weight / 100

    result["calculated_score"] = round(weighted_total)
    result["interview_metadata"] = {
        "total_rounds": len(turns),
        "covered_dimensions": interview_data.get("covered_dimensions", []),
        "timestamp": interview_data.get("timestamp", ""),
    }

    return result


def format_report_for_display(report: dict) -> dict:
    """
    将报告格式化为前端展示友好的结构。
    """
    dim_scores = report.get("dimension_scores", {})

    # 雷达图数据
    radar_data = {
        "labels": [],
        "scores": [],
        "weights": [],
    }
    for key, dim in dim_scores.items():
        label_map = {
            "job_match": "岗位匹配度",
            "technical_ability": "技术能力",
            "communication": "沟通表达",
            "comprehensive_quality": "综合素质",
            "integrity": "诚信度",
        }
        radar_data["labels"].append(label_map.get(key, key))
        radar_data["scores"].append(dim.get("score", 0))
        radar_data["weights"].append(dim.get("weight", 20))

    # 推荐级别映射
    rec_map = {
        "strong_hire": "强烈推荐",
        "hire": "推荐录用",
        "hold": "待定",
        "no_hire": "不推荐",
    }
    recommendation = report.get("recommendation", "hold")

    return {
        "overall_score": report.get("calculated_score", report.get("overall_score", 0)),
        "recommendation": rec_map.get(recommendation, recommendation),
        "summary": report.get("summary", ""),
        "radar_data": radar_data,
        "dimension_scores": dim_scores,
        "highlights": report.get("highlights", []),
        "concerns": report.get("concerns", []),
        "contradictions": report.get("contradictions", []),
        "question_review": report.get("question_review", []),
        "next_round_suggestions": report.get("next_round_suggestions", []),
        "overall_comment": report.get("overall_comment", ""),
        "metadata": report.get("interview_metadata", {}),
    }
