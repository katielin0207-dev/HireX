"""Interview evaluation generation for the B module."""
from __future__ import annotations

import re

from app.shared import call_llm, demo_mode_enabled, load_demo_cache


DIMENSIONS = ["专业能力", "项目深度", "沟通表达", "风险核验", "岗位匹配"]


def generate_interview_questions(candidate: dict, jd: dict | None = None, use_llm: bool = True) -> list[dict]:
    """Generate structured, personalized interview questions before the interview."""
    if demo_mode_enabled():
        cached = load_demo_cache(f"questions_{candidate.get('id')}")
        if cached:
            return cached

    if not use_llm:
        return _fallback_questions(candidate, jd or {})

    prompt = f"""请为候选人生成结构化面试题。

要求：
- 结合岗位类型、候选人简历短板、岗位核心考察点、风险报告
- 题目要适合企业 HR 和用人部门联合面试
- 只输出 JSON 数组，不要 Markdown
- 每道题包含 category/question/purpose/good_answer_signal/risk_to_verify

JSON 示例：
[
  {{
    "category": "专业能力",
    "question": "请描述一次你在制造现场推动工艺改善的经历。",
    "purpose": "验证现场工艺改善能力",
    "good_answer_signal": "能说清问题、数据、措施和结果",
    "risk_to_verify": "项目贡献是否真实"
  }}
]

【JD】
{(jd or {}).get("raw_text", "")[:1200]}

【候选人】
姓名：{candidate.get("name")}
简历解析：{candidate.get("resume_parsed")}
匹配结果：{candidate.get("match_result")}
风险报告：{candidate.get("risk_report")}
"""
    try:
        result = call_llm(
            prompt,
            system="你是资深招聘面试官助手。只输出合法 JSON 数组。",
            expect_json=True,
            temperature=0.25,
            max_retries=2,
        )
        if isinstance(result, dict):
            result = result.get("questions") or []
        if isinstance(result, list) and result:
            return [_normalize_question(q) for q in result if isinstance(q, dict)][:10]
    except Exception:  # noqa: BLE001
        pass
    return _fallback_questions(candidate, jd or {})


def generate_interview_eval(candidate: dict, interview_notes: str, jd: dict | None = None, use_llm: bool = True) -> dict:
    """Generate candidate["interview_eval"] from interview notes."""
    if demo_mode_enabled():
        cached = load_demo_cache(f"eval_{candidate.get('id')}")
        if cached:
            return cached

    notes = (interview_notes or "").strip()
    if not notes:
        raise ValueError("请先粘贴面试记录，再生成评价表")

    if not use_llm:
        return _fallback_eval(candidate, notes)

    prompt = f"""请根据 JD、候选人匹配结果、风险报告和面试记录，生成结构化面试评价表。

要求：
- 只输出 JSON，不要输出 Markdown
- 分数为 0-100 的整数
- 评价必须引用面试记录中的具体表现
- 风险核验要回应 risk_report 中的关注点

JSON 格式：
{{
  "rating": "A|B|C|D",
  "dimension_scores": {{
    "专业能力": 85,
    "项目深度": 80,
    "沟通表达": 78,
    "风险核验": 70,
    "岗位匹配": 82
  }},
  "summary": "面试表现总结，80字以内",
  "concerns": ["关注点1", "关注点2"],
  "form_filled": {{
    "面试结论": "通过|待定|不通过",
    "推荐动作": "进入下一轮|补充核验|暂不推进",
    "面试官备注": "可直接写入系统的话"
  }}
}}

【JD】
{(jd or {}).get("raw_text", "")[:1200]}

【候选人】
姓名：{candidate.get("name")}
匹配结果：{candidate.get("match_result")}
风险报告：{candidate.get("risk_report")}

【面试记录】
{notes[:2500]}
"""
    try:
        result = call_llm(
            prompt,
            system="你是企业招聘面试官助手，擅长把面试记录整理为客观评价表。只输出合法 JSON。",
            expect_json=True,
            temperature=0.2,
            max_retries=2,
        )
        return _normalize_eval(result, candidate, notes)
    except Exception:  # noqa: BLE001
        fallback = _fallback_eval(candidate, notes)
        fallback["concerns"].append("模型暂不可用，本次评价已使用本地规则生成，建议面试官复核。")
        return fallback


def _normalize_eval(result: dict, candidate: dict, notes: str) -> dict:
    if not isinstance(result, dict):
        return _fallback_eval(candidate, notes)
    scores = result.get("dimension_scores") or {}
    normalized_scores = {
        dim: _score(scores.get(dim, _default_score(candidate)))
        for dim in DIMENSIONS
    }
    rating = str(result.get("rating") or _rating(sum(normalized_scores.values()) / len(normalized_scores))).upper()
    if rating not in {"A", "B", "C", "D"}:
        rating = _rating(sum(normalized_scores.values()) / len(normalized_scores))

    form = result.get("form_filled") if isinstance(result.get("form_filled"), dict) else {}
    conclusion = form.get("面试结论") or _conclusion(rating)

    return {
        "rating": rating,
        "dimension_scores": normalized_scores,
        "summary": str(result.get("summary") or _summary(candidate, notes))[:180],
        "concerns": [str(x) for x in (result.get("concerns") or [])][:5],
        "form_filled": {
            "面试结论": conclusion,
            "推荐动作": form.get("推荐动作") or _next_step(rating),
            "面试官备注": form.get("面试官备注") or str(result.get("summary") or _summary(candidate, notes))[:160],
        },
    }


def _fallback_eval(candidate: dict, notes: str) -> dict:
    base = _default_score(candidate)
    positive = len(re.findall(r"清晰|深入|独立|主导|优化|高并发|落地|复盘|主动", notes))
    negative = len(re.findall(r"不清楚|模糊|无法|没有|欠缺|存疑|包装|回避", notes))
    score = max(45, min(95, base + positive * 3 - negative * 5))
    risk_level = (candidate.get("risk_report") or {}).get("level", "低")
    risk_score = score if risk_level == "低" else max(45, score - (12 if risk_level == "高" else 6))
    scores = {
        "专业能力": score,
        "项目深度": max(45, score - 4),
        "沟通表达": max(45, min(95, score + 2 if "清晰" in notes else score - 2)),
        "风险核验": risk_score,
        "岗位匹配": _default_score(candidate),
    }
    avg = sum(scores.values()) / len(scores)
    rating = _rating(avg)
    concerns = []
    if risk_level != "低":
        concerns.append(f"风险等级为{risk_level}，需补充核验后再推进")
    if negative:
        concerns.append("面试记录中存在表达模糊或证据不足的回答")
    if not concerns:
        concerns.append("建议下一轮继续验证项目复杂度和个人贡献边界")
    return {
        "rating": rating,
        "dimension_scores": scores,
        "summary": _summary(candidate, notes),
        "concerns": concerns[:5],
        "form_filled": {
            "面试结论": _conclusion(rating),
            "推荐动作": _next_step(rating),
            "面试官备注": _summary(candidate, notes),
        },
    }


def _fallback_questions(candidate: dict, jd: dict) -> list[dict]:
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    gaps = match.get("gap_points") or []
    focus = risk.get("interview_focus") or []
    title = (jd or {}).get("title", "目标岗位")
    questions = [
        {
            "category": "岗位动机",
            "question": f"你为什么选择应聘{title}？对这个岗位的一线工作场景有什么理解？",
            "purpose": "确认岗位认知和稳定性",
            "good_answer_signal": "能结合岗位职责说明动机，并接受真实工作强度",
            "risk_to_verify": "岗位期待是否偏差",
        },
        {
            "category": "专业能力",
            "question": "请讲一个你参与制造现场、工艺改善或质量问题分析的具体案例。",
            "purpose": "验证核心专业能力和真实参与度",
            "good_answer_signal": "能说清问题背景、数据证据、个人动作和改善结果",
            "risk_to_verify": "项目贡献是否真实",
        },
        {
            "category": "问题闭环",
            "question": "如果生产线连续出现同类不良，你会如何定位原因并推动闭环？",
            "purpose": "考察质量问题分析和跨部门协同",
            "good_answer_signal": "能使用 5Why、鱼骨图、数据分层、临时对策和长期对策",
            "risk_to_verify": "是否只会描述现象，缺少闭环思维",
        },
        {
            "category": "现场适应",
            "question": "如果需要阶段性深入产线、跟班或处理突发异常，你能接受到什么程度？",
            "purpose": "确认一线适应性和抗压能力",
            "good_answer_signal": "能明确表达接受边界，并理解制造现场节奏",
            "risk_to_verify": "一线意愿是否真实",
        },
    ]
    for gap in gaps[:3]:
        questions.append({
            "category": "简历短板",
            "question": f"你的简历中有这个差距：{gap}。请你补充说明相关经历或学习计划。",
            "purpose": "针对匹配差距做个性化追问",
            "good_answer_signal": "能正面回应短板，并给出证据或补足计划",
            "risk_to_verify": "短板是否影响胜任",
        })
    for item in focus[:3]:
        questions.append({
            "category": "风险核验",
            "question": item if str(item).endswith("？") else f"{item}，请候选人现场说明。",
            "purpose": "核验风险报告中的关键疑点",
            "good_answer_signal": "能提供可验证证据，而不是泛泛解释",
            "risk_to_verify": "风险是否可接受",
        })
    return questions[:10]


def _normalize_question(question: dict) -> dict:
    return {
        "category": str(question.get("category") or "综合考察"),
        "question": str(question.get("question") or ""),
        "purpose": str(question.get("purpose") or question.get("intent") or "验证候选人与岗位的匹配度"),
        "good_answer_signal": str(question.get("good_answer_signal") or "回答具体、有证据、有结果"),
        "risk_to_verify": str(question.get("risk_to_verify") or "暂无"),
    }


def _default_score(candidate: dict) -> int:
    match = candidate.get("match_result") or {}
    return _score(match.get("overall_score", 75))


def _score(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 75


def _rating(avg: float) -> str:
    if avg >= 85:
        return "A"
    if avg >= 75:
        return "B"
    if avg >= 60:
        return "C"
    return "D"


def _conclusion(rating: str) -> str:
    return {"A": "通过", "B": "通过", "C": "待定", "D": "不通过"}.get(rating, "待定")


def _next_step(rating: str) -> str:
    return {"A": "进入下一轮", "B": "进入下一轮", "C": "补充核验", "D": "暂不推进"}.get(rating, "补充核验")


def _summary(candidate: dict, notes: str) -> str:
    name = candidate.get("name", "候选人")
    short_notes = re.sub(r"\s+", " ", notes).strip()[:70]
    return f"{name}整体表现结合面试记录判断为可继续评估。关键表现：{short_notes}"
