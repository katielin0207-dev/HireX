"""人才评价聚合、人才标签与 Offer 备选推荐。纯数据逻辑，不调用 LLM。"""

import hashlib
import json
from typing import Iterable


RADAR_DIMENSIONS = {
    "技能": "skills_match",
    "经验": "experience_match",
    "学历": "education_match",
    "项目": "project_relevance",
}


def overall_score(candidate: dict) -> float:
    return float(candidate.get("match_result", {}).get("overall_score", 0) or 0)


def interview_score(candidate: dict) -> float | None:
    """取面试各维度平均分；未完成面试时返回 None，避免伪造评价。"""
    dimensions = (candidate.get("interview_eval") or {}).get("dimension_scores") or {}
    values = [float(value or 0) for value in dimensions.values()]
    return round(sum(values) / len(values), 1) if values else None


def decision_score(candidate: dict) -> float | None:
    """面试完成后生成综合决策分：匹配55% + 面试35% + 风险10%。"""
    interview = interview_score(candidate)
    if interview is None:
        return None
    risk_level = (candidate.get("risk_report") or {}).get("level", "未检测")
    risk_score = {"低": 100, "中": 60, "高": 20}.get(risk_level, 60)
    return round(overall_score(candidate) * 0.55 + interview * 0.35 + risk_score * 0.10, 1)


def display_stage(candidate: dict) -> str:
    """把底层状态翻译为 HR 能快速理解的招聘阶段。"""
    status = candidate.get("status", "new")
    if status == "hired":
        return "已入职·成功样本"
    if status == "offered":
        return "已发Offer"
    if status == "in_pool":
        return "人才库"
    if status == "declined":
        return "已放弃"
    if candidate.get("interview_eval") or status == "interviewed":
        return "待决策"
    return "待面试"


def is_pool_qualified(candidate: dict) -> bool:
    """MVP 入库门槛：匹配分不低于60且非高风险。"""
    return (
        bool(candidate.get("match_result"))
        and overall_score(candidate) >= 60
        and (candidate.get("risk_report") or {}).get("level") != "高"
        and candidate.get("status") not in {"offered", "declined", "hired"}
    )


def comparison_rows(candidates: Iterable[dict]) -> list[dict]:
    """生成页面表格需要的扁平结构，并按总分降序。"""
    rows = []
    for candidate in candidates:
        match = candidate.get("match_result") or {}
        risk = candidate.get("risk_report") or {}
        interview = candidate.get("interview_eval") or {}
        interview_avg = interview_score(candidate)
        decision = decision_score(candidate)
        rows.append(
            {
                "候选人": candidate.get("name", candidate.get("id", "-")),
                "匹配总分": match.get("overall_score", 0),
                "面试得分": interview_avg if interview_avg is not None else "待面试",
                "综合决策分": decision if decision is not None else "待面试",
                "风险等级": risk.get("level", "未检测"),
                "面试评级": interview.get("rating", "未面试"),
                "招聘阶段": display_stage(candidate),
                "标签": "、".join(candidate.get("tags") or []),
            }
        )
    return sorted(rows, key=lambda row: float(row["匹配总分"] or 0), reverse=True)


def radar_scores(candidate: dict) -> dict[str, float]:
    breakdown = (candidate.get("match_result") or {}).get("breakdown") or {}
    return {
        label: float((breakdown.get(key) or {}).get("score", 0) or 0)
        for label, key in RADAR_DIMENSIONS.items()
    }


def recommend_backups(candidates: Iterable[dict], declined_id: str) -> list[dict]:
    """排除放弃者和高风险者，按匹配分推荐仍可推进的候选人。"""
    excluded_statuses = {"declined", "offered", "hired"}
    backups = []
    for candidate in candidates:
        if candidate.get("id") == declined_id:
            continue
        if candidate.get("status") in excluded_statuses:
            continue
        if (candidate.get("risk_report") or {}).get("level") == "高":
            continue
        if not candidate.get("match_result"):
            continue
        backups.append(candidate)
    return sorted(backups, key=overall_score, reverse=True)


def jd_signature(jd: dict) -> str:
    """生成稳定的 JD 指纹；JD 内容变化后，人才复用优先级会自动重算。"""
    payload = json.dumps(jd or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _job_direction(title: str) -> str:
    lowered = title.lower()
    if any(word in lowered for word in ("质量", "ie", "品控", "体系")):
        return "质量/IE方向"
    if any(word in lowered for word in ("制造", "工艺", "生产", "设备", "精益")):
        return "制造/工艺方向"
    if any(word in lowered for word in ("工程师", "技术", "开发", "研发", "算法", "软件", "硬件")):
        return "工程师/技术方向"
    return "职能/非技术方向"


def _tag(label: str, source: str, evidence: str, reason: str, confidence: int = 88) -> dict:
    return {
        "label": label,
        "source": source,
        "evidence": evidence,
        "reason": reason,
        "confidence": confidence,
    }


def _dedupe_tags(tags: list[dict], limit: int = 3) -> list[dict]:
    result = []
    seen = set()
    for tag in tags:
        key = str(tag.get("label", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(tag)
        if len(result) >= limit:
            break
    return result


def _evidence_completeness(candidate: dict) -> float:
    parsed = candidate.get("resume_parsed") or {}
    match = candidate.get("match_result") or {}
    interview = candidate.get("interview_eval") or {}
    checks = [
        bool(parsed.get("education")),
        bool(parsed.get("experience")),
        bool(parsed.get("skills")),
        bool(match.get("summary") or match.get("breakdown")),
        bool(interview.get("summary")),
        bool(interview.get("dimension_scores")),
    ]
    return round(sum(checks) / len(checks) * 100, 1)


def _reuse_priority(candidate: dict) -> dict:
    match = candidate.get("match_result") or {}
    current_match = overall_score(candidate)
    historical_interview = interview_score(candidate)
    if historical_interview is None:
        historical_interview = float(match.get("soft_score", current_match) or current_match)
    completeness = _evidence_completeness(candidate)
    hard_score = float(match.get("hard_score", 0) or 0)
    hard_gate = hard_score >= 60
    score = round(current_match * 0.60 + historical_interview * 0.25 + completeness * 0.15, 1)
    if not hard_gate:
        score = min(score, 59.0)
    if score >= 85:
        level = "优先联系"
    elif score >= 70:
        level = "建议复用"
    elif score >= 60:
        level = "培养型储备"
    else:
        level = "暂不推荐"
    return {
        "score": score,
        "level": level,
        "hard_gate": hard_gate,
        "components": {
            "当前JD匹配": round(current_match, 1),
            "历史面试": round(historical_interview, 1),
            "证据完整度": completeness,
        },
        "explanation": (
            f"按当前JD匹配60%、历史面试25%、证据完整度15%计算；"
            f"硬性门槛{'通过' if hard_gate else '未通过'}。"
        ),
    }


def generate_talent_profile(candidate: dict, jd: dict) -> dict:
    """生成四类可追溯人才标签和当前岗位复用优先级。

    这是确定性规则层，便于 Demo 稳定运行；后续可将标签候选交给模型扩写，
    但字段契约无需变化。
    """
    parsed = candidate.get("resume_parsed") or {}
    match = candidate.get("match_result") or {}
    interview = candidate.get("interview_eval") or {}
    experiences = parsed.get("experience") or []
    current_experience = experiences[0] if experiences else {}
    current_title = str(current_experience.get("title") or "岗位经历待完善")
    company = str(current_experience.get("company") or "公司信息待完善")
    jd_title = str((jd or {}).get("title") or "当前岗位")

    direction = _job_direction(jd_title)
    direction_tags = [
        _tag(
            direction,
            "当前JD + 简历工作经历",
            f"当前JD：{jd_title}；候选人最近岗位：{company}·{current_title}",
            "AI结合当前招聘岗位和候选人最近岗位，归纳可复用的岗位方向。",
            94,
        )
    ]

    skills = [str(skill) for skill in (parsed.get("skills") or []) if str(skill).strip()]
    hard = ((jd or {}).get("requirements") or {}).get("hard") or {}
    jd_skills = [str(skill) for skill in (hard.get("must_skills") or []) if str(skill).strip()]
    jd_skill_map = {skill.lower(): skill for skill in jd_skills}
    matched_skills = [skill for skill in skills if skill.lower() in jd_skill_map]
    selected_skills = matched_skills[:3] or skills[:3]
    skill_tags = [
        _tag(
            skill,
            "简历技能栏 + 当前JD",
            f"简历技能栏明确列出“{skill}”；当前JD核心技能：{'、'.join(jd_skills[:7]) or '待配置'}。",
            "AI优先保留与当前JD直接重合的专业技能；无重合时仅作为历史能力标签。",
            96 if skill in matched_skills else 82,
        )
        for skill in selected_skills
    ]

    years = float(parsed.get("total_years", 0) or 0)
    years_label = f"{years:g}年经验" if years else "经验年限待完善"
    experience_tags = [
        _tag(
            years_label,
            "简历工作经历",
            f"系统根据简历经历区间汇总为 {years:g} 年；最近经历为 {company}·{current_title}。" if years else f"最近经历为 {company}·{current_title}，年限待核验。",
            "AI将履历时间线汇总为可检索的经验年限标签。",
            93 if years else 62,
        ),
        _tag(
            _job_direction(current_title).replace("方向", "经验"),
            "简历工作经历",
            f"候选人最近岗位为 {company}·{current_title}。",
            "AI依据最近岗位名称归纳行业/岗位经验背景，供跨岗位复用检索。",
            86,
        ),
    ]

    dimension_scores = interview.get("dimension_scores") or {}
    competency_tags = []
    for label, score in sorted(dimension_scores.items(), key=lambda item: float(item[1] or 0), reverse=True):
        if float(score or 0) < 70:
            continue
        competency_tags.append(
            _tag(
                str(label),
                "结构化面试评价",
                f"面试维度“{label}”得分 {float(score):g}/100；面试总结：{interview.get('summary') or '待补充'}",
                "AI从已提交的结构化面试评分中提取稳定的通用能力标签。",
                min(98, round(float(score))),
            )
        )
    if not competency_tags:
        soft_requirements = ((jd or {}).get("requirements") or {}).get("soft") or []
        soft_score = float(match.get("soft_score", 0) or 0)
        competency_tags = [
            _tag(
                str(label),
                "简历软性匹配",
                f"当前JD要求“{label}”；简历软性匹配得分 {soft_score:g}/100。",
                "当前仅有简历侧线索，入库后应在结构化面试中继续验证。",
                68,
            )
            for label in soft_requirements[:2]
        ]

    categories = [
        {"key": "job_direction", "label": "岗位方向", "tags": _dedupe_tags(direction_tags, 1)},
        {"key": "professional_skills", "label": "专业技能", "tags": _dedupe_tags(skill_tags, 3)},
        {"key": "experience_background", "label": "经验背景", "tags": _dedupe_tags(experience_tags, 2)},
        {"key": "general_competency", "label": "通用能力", "tags": _dedupe_tags(competency_tags, 2)},
    ]
    return {
        "version": 1,
        "jd_signature": jd_signature(jd or {}),
        "generated_for": {"title": jd_title},
        "categories": categories,
        "reuse_priority": _reuse_priority(candidate),
    }


def talent_tag_labels(profile: dict) -> list[str]:
    """为搜索与导出提供扁平标签列表。"""
    return [
        str(tag.get("label", ""))
        for category in (profile or {}).get("categories") or []
        for tag in category.get("tags") or []
        if tag.get("label")
    ]
