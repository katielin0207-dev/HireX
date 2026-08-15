"""成功候选人回流：把录用结果转为可解释、可人工确认的岗位画像建议。"""

from copy import deepcopy
from datetime import datetime
import json


SYSTEM_PROMPT = """你是企业招聘岗位画像优化助手。
只根据输入的岗位要求、候选人简历事实、匹配结果和面试评价提出建议。
不得推断受保护属性，不得把单个成功样本包装成统计规律，不得自动作出招聘决定。
只输出合法 JSON。"""


def _current_weights(jd: dict) -> dict:
    weights = jd.get("weights") or {
        "degree": 0.20, "years": 0.20, "skills": 0.40, "soft": 0.20,
    }
    result = {key: round(float(weights.get(key, 0) or 0), 2)
              for key in ("degree", "years", "skills", "soft")}
    total = sum(result.values())
    if total <= 0:
        return {"degree": 0.20, "years": 0.20, "skills": 0.40, "soft": 0.20}
    return {key: round(value / total, 2) for key, value in result.items()}


def _first_new_skill(candidate: dict, jd: dict) -> str:
    parsed = candidate.get("resume_parsed") or {}
    candidate_skills = [str(skill).strip() for skill in (parsed.get("skills") or []) if str(skill).strip()]
    current = {
        str(skill).strip().lower()
        for skill in (((jd.get("requirements") or {}).get("hard") or {}).get("must_skills") or [])
    }
    return next((skill for skill in candidate_skills if skill.lower() not in current), "岗位核心方法论")


def fallback_success_feedback(candidate: dict, jd: dict) -> list[dict]:
    """API不可用时的可解释兜底；所有建议仍需HR确认。"""
    parsed = candidate.get("resume_parsed") or {}
    interview = candidate.get("interview_eval") or {}
    match = candidate.get("match_result") or {}
    education = parsed.get("education") or []
    experience = parsed.get("experience") or []
    new_skill = _first_new_skill(candidate, jd)
    current_weights = _current_weights(jd)
    adjusted_weights = dict(current_weights)
    # 单样本只做小幅建议，且保持总和100%。
    shift = min(0.05, adjusted_weights.get("degree", 0.20))
    adjusted_weights["degree"] = round(adjusted_weights.get("degree", 0.20) - shift, 2)
    adjusted_weights["skills"] = round(adjusted_weights.get("skills", 0.40) + shift, 2)
    dimension_scores = interview.get("dimension_scores") or {}
    strongest_dimension = max(dimension_scores, key=dimension_scores.get) if dimension_scores else "问题解决"
    soft_value = "问题分析与闭环推动" if "问题" in strongest_dimension else strongest_dimension

    edu_quote = "；".join(
        f"{item.get('school', '院校待完善')}·{item.get('degree', '学历待完善')}·{item.get('major', '专业待完善')}"
        for item in education[:2]
    ) or "简历未提供完整教育信息"
    exp_quote = "；".join(
        f"{item.get('company', '公司待完善')}·{item.get('title', '岗位待完善')}"
        for item in experience[:2]
    ) or "简历未提供完整工作经历"
    matched_quote = "；".join(match.get("matched_points") or []) or match.get("summary") or "暂无明确匹配证据"
    interview_quote = interview.get("summary") or "尚未形成完整面试评价"

    return [
        {
            "id": "skill_add",
            "type": "核心技能",
            "title": f"建议复核是否将“{new_skill}”纳入岗位技能",
            "before": "当前必备技能未包含该项",
            "after": f"下一版岗位模板增加：{new_skill}",
            "rationale": "该能力出现在成功候选人的真实履历中，但单个样本不足以直接升级为硬门槛，建议结合更多录用样本复核。",
            "evidence": [
                {"source": "成功候选人·简历技能", "quote": new_skill},
                {"source": "成功候选人·匹配结论", "quote": matched_quote},
            ],
            "impact": "采纳后仅影响下一轮同岗位筛选，不修改历史结果。",
            "action": {"kind": "add_skill", "value": new_skill},
            "decision": "pending",
        },
        {
            "id": "weight_adjust",
            "type": "评分权重",
            "title": "建议小幅提高技能权重、降低学历权重",
            "before": _weight_text(current_weights),
            "after": _weight_text(adjusted_weights),
            "rationale": "成功候选人的岗位匹配与面试证据更集中在实际技能和经历，建议仅做5个百分点以内的小幅校准。",
            "evidence": [
                {"source": "成功候选人·教育经历", "quote": edu_quote},
                {"source": "成功候选人·工作经历", "quote": exp_quote},
            ],
            "impact": "采纳后更新岗位默认模板；权重总和仍保持100%。",
            "action": {"kind": "set_weights", "value": adjusted_weights},
            "decision": "pending",
        },
        {
            "id": "soft_add",
            "type": "面试重点",
            "title": f"建议将“{soft_value}”加入结构化面试重点",
            "before": "当前岗位画像未单独强调该能力",
            "after": f"下一轮面试重点增加：{soft_value}",
            "rationale": "该维度在成功候选人的面试评价中表现突出，可作为后续同岗位候选人的核验方向，但不直接设为淘汰条件。",
            "evidence": [
                {"source": "成功候选人·面试评价", "quote": interview_quote},
                {"source": "成功候选人·面试维度", "quote": json.dumps(dimension_scores, ensure_ascii=False)},
            ],
            "impact": "采纳后加入下一轮岗位软实力要求与面试题生成上下文。",
            "action": {"kind": "add_soft", "value": soft_value},
            "decision": "pending",
        },
    ]


def _weight_text(weights: dict) -> str:
    labels = {"degree": "学历", "years": "经验", "skills": "技能", "soft": "软实力"}
    return " · ".join(f"{labels[key]} {round(value * 100)}%" for key, value in weights.items())


def _normalize_suggestions(result, fallback: list[dict]) -> list[dict]:
    suggestions = result.get("suggestions") if isinstance(result, dict) else None
    if not isinstance(suggestions, list) or not suggestions:
        return fallback
    allowed_kinds = {"add_skill", "add_soft", "set_weights"}
    normalized = []
    for index, item in enumerate(suggestions[:3]):
        if not isinstance(item, dict):
            continue
        action = item.get("action") or {}
        kind = action.get("kind")
        if kind not in allowed_kinds:
            continue
        value = action.get("value")
        if kind == "set_weights":
            if not isinstance(value, dict):
                continue
            try:
                weights = {key: float(value[key]) for key in WEIGHT_KEYS}
            except (KeyError, TypeError, ValueError):
                continue
            if any(weight < 0 for weight in weights.values()) or abs(sum(weights.values()) - 1) > 0.001:
                continue
            action = {"kind": kind, "value": weights}
        elif not str(value or "").strip():
            continue
        else:
            action = {"kind": kind, "value": str(value).strip()}
        evidence = item.get("evidence") or []
        if not isinstance(evidence, list) or not evidence:
            continue
        normalized.append({
            "id": str(item.get("id") or f"ai_{index}"),
            "type": str(item.get("type") or "岗位画像"),
            "title": str(item.get("title") or "岗位画像优化建议"),
            "before": str(item.get("before") or "当前模板"),
            "after": str(item.get("after") or "建议模板"),
            "rationale": str(item.get("rationale") or "根据成功候选人材料生成，需HR复核。"),
            "evidence": [
                {"source": str(ev.get("source") or "候选人材料"),
                 "quote": str(ev.get("quote") or "待复核")}
                for ev in evidence[:3] if isinstance(ev, dict)
            ],
            "impact": str(item.get("impact") or "仅影响下一轮岗位模板。"),
            "action": action,
            "decision": "pending",
        })
    return normalized or fallback


def generate_success_feedback(candidate: dict, jd: dict, llm_caller=None) -> dict:
    """生成三条岗位画像建议；真实AI失败时返回有证据的本地兜底。"""
    fallback = fallback_success_feedback(candidate, jd)
    if llm_caller is None:
        from app.shared import call_llm
        llm_caller = call_llm

    safe_candidate = {
        "resume_parsed": candidate.get("resume_parsed") or {},
        "match_result": candidate.get("match_result") or {},
        "interview_eval": candidate.get("interview_eval") or {},
        "risk_report": candidate.get("risk_report") or {},
    }
    prompt = f"""请根据一个已通过试用期的成功候选人，为下一轮同岗位招聘生成3条可人工确认的岗位画像优化建议。

【当前岗位】
{json.dumps(jd, ensure_ascii=False)}

【成功候选人去标识化材料】
{json.dumps(safe_candidate, ensure_ascii=False)}

输出JSON：
{{"suggestions":[{{
  "id":"唯一短标识",
  "type":"核心技能/评分权重/面试重点",
  "title":"建议标题",
  "before":"修改前",
  "after":"修改后",
  "rationale":"为什么建议，必须注明单个样本只作参考",
  "evidence":[{{"source":"简历/面试具体来源","quote":"输入材料中的原文或事实"}}],
  "impact":"采纳后影响范围",
  "action":{{"kind":"add_skill/add_soft/set_weights","value":"字符串或四维权重对象"}}
}}]}}

要求：建议必须有输入证据；set_weights的degree/years/skills/soft总和必须为1；不得使用姓名、性别、年龄等受保护属性。"""
    try:
        result = llm_caller(prompt, system=SYSTEM_PROMPT, expect_json=True, max_retries=1)
        suggestions = _normalize_suggestions(result, fallback)
        origin = "AI生成"
    except Exception:
        suggestions = fallback
        origin = "本地证据规则兜底"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "origin": origin,
        "sample_scope": "单个成功样本，仅供下一轮岗位模板优化参考",
        "suggestions": suggestions,
    }


def apply_feedback_to_jd(jd: dict, suggestion: dict) -> dict:
    """把HR已采纳的单条建议应用到下一版JD副本。"""
    updated = deepcopy(jd or {})
    action = suggestion.get("action") or {}
    kind = action.get("kind")
    value = action.get("value")
    requirements = updated.setdefault("requirements", {})
    hard = requirements.setdefault("hard", {})

    if kind == "add_skill" and str(value).strip():
        skills = hard.setdefault("must_skills", [])
        if str(value).strip().lower() not in {str(item).strip().lower() for item in skills}:
            skills.append(str(value).strip())
    elif kind == "add_soft" and str(value).strip():
        soft = requirements.setdefault("soft", [])
        if str(value).strip().lower() not in {str(item).strip().lower() for item in soft}:
            soft.append(str(value).strip())
    elif kind == "set_weights" and isinstance(value, dict):
        keys = ("degree", "years", "skills", "soft")
        weights = {key: round(float(value.get(key, 0) or 0), 2) for key in keys}
        if abs(sum(weights.values()) - 1.0) > 0.011 or any(weight < 0 for weight in weights.values()):
            raise ValueError("权重建议必须为非负数且总和等于1")
        updated["weights"] = weights
    else:
        raise ValueError("不支持的岗位画像更新动作")

    updated["feedback_updated_at"] = datetime.now().isoformat(timespec="seconds")
    updated["generation_status"] = "success_sample_optimized_draft"
    return updated
