"""候选人专属面试包与面试评价生成。"""

from __future__ import annotations

import re

from app.shared import call_llm, demo_mode_enabled, load_demo_cache, save_demo_cache


QUESTION_PLAN = [
    ("专业能力", 3),
    ("项目核验", 2),
    ("风险追问", 2),
    ("软实力", 1),
    ("综合判断", 1),
]


def build_candidate_interview_context(candidate: dict, jd: dict) -> dict:
    """不修改公开JD，生成该候选人的专属面试上下文。"""
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    return {
        "job": {
            "title": jd.get("title", "目标岗位"),
            "raw_text": jd.get("raw_text", ""),
            "requirements": jd.get("requirements", {}),
        },
        "candidate": {
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "resume": candidate.get("resume_parsed") or {},
            "resume_text": candidate.get("resume_text", ""),
        },
        "screening": {
            "overall_score": match.get("overall_score"),
            "matched_points": match.get("matched_points") or [],
            "gap_points": match.get("gap_points") or [],
            "summary": match.get("summary", ""),
        },
        "risk": {
            "level": risk.get("level", "未核验"),
            "risks": risk.get("risks") or [],
            "interview_focus": risk.get("interview_focus") or [],
        },
        "assessment": candidate.get("assessment_report") or {},
        "phone_screen": candidate.get("phone_screen") or {},
    }


def generate_interview_questions(candidate: dict, jd: dict, use_llm: bool = True) -> list[dict]:
    cache_name = f"questions_{candidate.get('id')}"
    if demo_mode_enabled():
        cached = load_demo_cache(cache_name)
        if cached:
            return _ensure_nine(cached, candidate, jd)

    if use_llm:
        context = build_candidate_interview_context(candidate, jd)
        prompt = f"""请根据候选人专属面试上下文生成严格9道结构化面试题。

数量和结构必须完全符合：
- 专业能力3道
- 项目核验2道
- 风险追问2道
- 软实力1道
- 综合判断1道

每道题包含 category、question、purpose、good_answer_signal、risk_to_verify。
问题必须引用岗位要求、候选人经历、匹配短板或风险点，不得编造经历。
只输出JSON：{{"questions":[...]}}

候选人专属上下文：{context}"""
        try:
            result = call_llm(
                prompt,
                system="你是制造业企业的结构化面试专家，只输出JSON。",
                expect_json=True,
                temperature=0.2,
                max_retries=2,
            )
            questions = result.get("questions", []) if isinstance(result, dict) else result
            questions = _ensure_nine(questions, candidate, jd)
            save_demo_cache(cache_name, questions)
            return questions
        except Exception:
            pass
    return _fallback_questions(candidate, jd)


def generate_interview_eval(
    candidate: dict, interview_notes: str, jd: dict, use_llm: bool = True
) -> dict:
    notes = (interview_notes or "").strip()
    context = build_candidate_interview_context(candidate, jd)
    if use_llm and notes:
        prompt = f"""请结合候选人专属上下文和面试记录，生成有证据的面试评价。
不得因线下面试记录本身额外加分；只能依据候选人的回答内容评分。

输出JSON：
{{
  "rating":"A|B|C|D",
  "dimension_scores":{{"专业能力":0,"项目深度":0,"沟通表达":0,"风险核验":0,"岗位匹配":0}},
  "summary":"面试纪要和结论",
  "concerns":["关注点"],
  "evidence":["支持结论的回答原文"],
  "form_filled":{{"面试结论":"通过|待定|不通过","推荐动作":"进入下一轮|补充核验|暂不推进","面试官备注":"可回写招聘系统的内容"}}
}}

候选人专属上下文：{context}
面试记录：{notes[:8000]}"""
        try:
            result = call_llm(
                prompt,
                system="你是严谨的企业面试评价助手，只输出JSON。",
                expect_json=True,
                temperature=0.2,
                max_retries=2,
            )
            return _normalize_eval(result, candidate, notes)
        except Exception:
            pass
    return _fallback_eval(candidate, notes)


def _ensure_nine(questions, candidate: dict, jd: dict) -> list[dict]:
    source = [q for q in (questions or []) if isinstance(q, dict) and q.get("question")]
    fallback = _fallback_questions(candidate, jd)
    output = []
    used = set()
    for category, count in QUESTION_PLAN:
        matching = [q for q in source if str(q.get("category", "")) == category]
        matching.extend(q for q in fallback if q["category"] == category)
        for question in matching:
            text = str(question.get("question", ""))
            if not text or text in used:
                continue
            used.add(text)
            output.append(_normalize_question(question, category))
            if sum(q["category"] == category for q in output) >= count:
                break
    return output[:9]


def _normalize_question(question: dict, category: str) -> dict:
    return {
        "category": category,
        "question": str(question.get("question") or ""),
        "purpose": str(question.get("purpose") or "验证岗位胜任力"),
        "good_answer_signal": str(question.get("good_answer_signal") or "回答具体、有证据、有个人动作和结果"),
        "risk_to_verify": str(question.get("risk_to_verify") or "暂无"),
    }


def _fallback_questions(candidate: dict, jd: dict) -> list[dict]:
    title = jd.get("title", "目标岗位")
    parsed = candidate.get("resume_parsed") or {}
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    skills = "、".join((parsed.get("skills") or [])[:5]) or "岗位核心技能"
    gaps = match.get("gap_points") or ["尚未充分证明的岗位能力"]
    focus = risk.get("interview_focus") or ["核心经历的真实性", "任职稳定性"]
    questions = [
        _q("专业能力", f"请说明你对{title}核心职责的理解，并结合{skills}描述你的实际使用深度。", "验证专业知识与岗位理解"),
        _q("专业能力", "遇到质量或业务指标连续异常时，你会如何定位根因并推动闭环？", "验证系统分析与问题闭环能力"),
        _q("专业能力", "请举例说明你如何在时间、质量和跨部门资源冲突时做取舍。", "验证复杂场景下的专业判断"),
        _q("项目核验", "选择一个最相关项目，按背景、个人任务、具体行动和量化结果完整说明。", "核验项目真实性及个人贡献"),
        _q("项目核验", "如果把刚才的项目重新做一次，你会改变哪个关键决策？为什么？", "验证复盘深度而非背诵经历"),
        _q("风险追问", f"针对“{gaps[0]}”，请补充可验证的项目、数据或材料。", "核验简历短板", gaps[0]),
        _q("风险追问", f"风险核验建议关注“{focus[0]}”。请作出具体说明，并提供可以交叉验证的信息。", "核验风险点", focus[0]),
        _q("软实力", "请讲一次你推动不同意见的同事共同解决问题的经历，你具体做了什么？", "考察沟通协作和影响力"),
        _q("综合判断", f"如果入职{title}，前90天你准备解决什么问题，如何衡量是否成功？", "判断岗位动机、计划性和落地能力"),
    ]
    return questions


def _q(category: str, question: str, purpose: str, risk: str = "暂无") -> dict:
    return {
        "category": category,
        "question": question,
        "purpose": purpose,
        "good_answer_signal": "回答具体，能说明个人动作、证据和量化结果",
        "risk_to_verify": risk,
    }


def _normalize_eval(result: dict, candidate: dict, notes: str) -> dict:
    if not isinstance(result, dict):
        return _fallback_eval(candidate, notes)
    dimensions = result.get("dimension_scores") or {}
    normalized = {}
    for name in ("专业能力", "项目深度", "沟通表达", "风险核验", "岗位匹配"):
        try:
            normalized[name] = max(0, min(100, int(float(dimensions.get(name, 0)))))
        except (TypeError, ValueError):
            normalized[name] = 0
    return {
        "rating": str(result.get("rating") or _rating(normalized.values())),
        "dimension_scores": normalized,
        "summary": str(result.get("summary") or "面试信息不足，建议人工补充。")[:500],
        "concerns": [str(x) for x in (result.get("concerns") or [])][:6],
        "evidence": [str(x) for x in (result.get("evidence") or [])][:6],
        "form_filled": result.get("form_filled") or {},
    }


def _fallback_eval(candidate: dict, notes: str) -> dict:
    base = float((candidate.get("match_result") or {}).get("overall_score", 70) or 70)
    positive = len(re.findall(r"主导|优化|降低|提升|闭环|数据|复盘|协同", notes))
    negative = len(re.findall(r"不清楚|没有|模糊|无法|回避", notes))
    score = int(max(45, min(92, base + positive * 2 - negative * 4)))
    dimensions = {
        "专业能力": score,
        "项目深度": max(45, score - 3),
        "沟通表达": max(45, score - 1),
        "风险核验": max(45, score - (8 if (candidate.get("risk_report") or {}).get("level") == "高" else 0)),
        "岗位匹配": int(base),
    }
    rating = _rating(dimensions.values())
    conclusion = "通过" if rating in {"A", "B"} else "待定" if rating == "C" else "不通过"
    return {
        "rating": rating,
        "dimension_scores": dimensions,
        "summary": "已根据面试记录形成初步评价，需面试官复核后提交。",
        "concerns": (candidate.get("risk_report") or {}).get("interview_focus", [])[:3],
        "evidence": [],
        "form_filled": {
            "面试结论": conclusion,
            "推荐动作": "进入下一轮" if conclusion == "通过" else "补充核验" if conclusion == "待定" else "暂不推进",
            "面试官备注": "系统初评，等待面试官确认。",
        },
    }


def _rating(values) -> str:
    values = list(values)
    average = sum(values) / len(values) if values else 0
    return "A" if average >= 85 else "B" if average >= 75 else "C" if average >= 60 else "D"
