"""Risk analysis for recruitment screening.

This module is intentionally lightweight for the hackathon MVP:
- deterministic rules catch timeline gaps, frequent job changes and expired certificates
- one optional LLM call adds "suspicious information" and "skill authenticity" checks
- output follows docs/CONTRACT.md: candidate["risk_report"]
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.shared import call_llm, demo_mode_enabled, load_demo_cache


HIGH_GAP_MONTHS = 12
MEDIUM_GAP_MONTHS = 6


def analyze_risk(candidate: dict, jd: dict | None = None, use_llm: bool = True) -> dict:
    """Return a contract-compatible risk_report for one candidate."""
    if demo_mode_enabled():
        cached = load_demo_cache(f"risk_{candidate.get('id')}")
        if cached:
            return cached

    risks: list[dict] = []
    risks.extend(_timeline_gap_risks(candidate))
    risks.extend(_job_hopping_risks(candidate))
    risks.extend(_certificate_risks(candidate))

    if use_llm:
        risks.extend(_llm_risks(candidate, jd or {}))

    risks = _dedupe_risks(risks)
    level = _risk_level(risks)
    focus = _interview_focus(candidate, risks)

    return {
        "level": level,
        "risks": risks,
        "interview_focus": focus,
    }


def _timeline_gap_risks(candidate: dict) -> list[dict]:
    experiences = candidate.get("resume_parsed", {}).get("experience") or []
    spans = []
    for exp in experiences:
        start = _parse_month(exp.get("start"))
        end = _parse_month(exp.get("end"), ongoing_as_today=True)
        if start and end:
            spans.append((start, end, exp))
    spans.sort(key=lambda item: item[0])

    risks = []
    for idx in range(len(spans) - 1):
        prev_start, prev_end, prev_exp = spans[idx]
        next_start, _next_end, next_exp = spans[idx + 1]
        gap = _months_between(prev_end, next_start) - 1
        if gap >= MEDIUM_GAP_MONTHS:
            severity = "high" if gap >= HIGH_GAP_MONTHS else "medium"
            risks.append({
                "type": "经历断层",
                "severity": severity,
                "detail": f"{_fmt_next_month(prev_end)}-{_fmt_prev_month(next_start)} 共 {_fmt_months(gap)}无工作经历，需核实原因",
                "evidence": (
                    f"{prev_exp.get('start', '')}-{prev_exp.get('end', '')} {prev_exp.get('company', '')}"
                    f" -> {next_exp.get('start', '')}-{next_exp.get('end', '')} {next_exp.get('company', '')}"
                ),
            })
    return risks


def _job_hopping_risks(candidate: dict) -> list[dict]:
    experiences = candidate.get("resume_parsed", {}).get("experience") or []
    short_jobs = []
    valid_spans = []
    for exp in experiences:
        start = _parse_month(exp.get("start"))
        end = _parse_month(exp.get("end"), ongoing_as_today=True)
        if not start or not end:
            continue
        months = max(1, _months_between(start, end) + 1)
        valid_spans.append(months)
        if months < 12:
            short_jobs.append((exp, months))

    risks = []
    if len(short_jobs) >= 2:
        risks.append({
            "type": "频繁跳槽",
            "severity": "medium",
            "detail": f"存在 {len(short_jobs)} 段不足 12 个月的工作经历，稳定性需进一步确认",
            "evidence": "；".join(
                f"{exp.get('company', '')} {exp.get('start', '')}-{exp.get('end', '')}（{months}个月）"
                for exp, months in short_jobs[:3]
            ),
        })
    elif len(valid_spans) >= 3 and sum(valid_spans) / len(valid_spans) < 14:
        risks.append({
            "type": "频繁跳槽",
            "severity": "low",
            "detail": "多段工作平均任职时间偏短，建议面试中确认离职原因",
            "evidence": f"共 {len(valid_spans)} 段经历，平均约 {round(sum(valid_spans) / len(valid_spans), 1)} 个月",
        })
    return risks


def _certificate_risks(candidate: dict) -> list[dict]:
    text = "\n".join([
        str(candidate.get("resume_text") or ""),
        str(candidate.get("resume_parsed") or ""),
        " ".join(map(str, candidate.get("tags") or [])),
    ])
    risks = []
    patterns = [
        r"(?P<cert>[\u4e00-\u9fa5A-Za-z0-9 +#-]{2,30}(?:证书|认证|资格证))[^。\n]{0,30}?(?:有效期至|到期|过期时间|有效至)[:：]?\s*(?P<date>20\d{2}[.\-/年](?:1[0-2]|0?[1-9]))",
        r"(?P<cert>[\u4e00-\u9fa5A-Za-z0-9 +#-]{2,30}(?:证书|认证|资格证))[^。\n]{0,20}?(?P<date>20\d{2}[.\-/年](?:1[0-2]|0?[1-9]))[^。\n]{0,10}?过期",
    ]
    for pat in patterns:
        for match in re.finditer(pat, text):
            expires = _parse_month(match.group("date"))
            if expires and expires < _month_index(date.today().year, date.today().month):
                risks.append({
                    "type": "证书过期",
                    "severity": "medium",
                    "detail": f"{match.group('cert').strip()}已过有效期，需核验证书状态",
                    "evidence": match.group(0),
                })
    return risks


def _llm_risks(candidate: dict, jd: dict) -> list[dict]:
    prompt = f"""请基于候选人简历和岗位要求，识别两类招聘风险：
1. 信息存疑：年限、项目规模、职责表述是否有明显夸大或前后不一致
2. 技能存疑：声称掌握的核心技能是否缺少项目证据

只输出 JSON，格式：
{{
  "risks": [
    {{"type": "信息存疑|技能存疑", "severity": "high|medium|low", "detail": "具体描述", "evidence": "引用简历中的证据"}}
  ]
}}

【岗位要求】
{(jd or {}).get("raw_text", "")[:1200]}

【候选人】
姓名：{candidate.get("name")}
简历解析：{candidate.get("resume_parsed")}
匹配结果：{candidate.get("match_result")}
简历原文：{str(candidate.get("resume_text") or "")[:1500]}
"""
    try:
        result = call_llm(
            prompt,
            system="你是资深招聘风控专家。只输出合法 JSON，不输出 Markdown。",
            expect_json=True,
            temperature=0.2,
            max_retries=2,
        )
    except Exception as exc:  # noqa: BLE001 - risk page must not fail because API is slow
        return [{
            "type": "信息存疑",
            "severity": "low",
            "detail": f"LLM 补充核验暂未完成：{str(exc)[:80]}",
            "evidence": "规则风控结果已生成，可稍后重试 AI 补充判断",
        }]

    risks = result.get("risks", []) if isinstance(result, dict) else []
    return [_normalize_risk(r) for r in risks if isinstance(r, dict)]


def _normalize_risk(risk: dict) -> dict:
    return {
        "type": str(risk.get("type") or "信息存疑"),
        "severity": _severity(risk.get("severity")),
        "detail": str(risk.get("detail") or risk.get("reason") or "需进一步核实"),
        "evidence": str(risk.get("evidence") or "未提供明确证据"),
    }


def _dedupe_risks(risks: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for risk in risks:
        item = _normalize_risk(risk)
        key = (item["type"], item["detail"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _risk_level(risks: list[dict]) -> str:
    severities = [r.get("severity") for r in risks]
    if "high" in severities:
        return "高"
    if severities.count("medium") >= 2 or "medium" in severities:
        return "中"
    return "低"


def _interview_focus(candidate: dict, risks: list[dict]) -> list[str]:
    focus = []
    for risk in risks:
        if risk["type"] == "经历断层":
            focus.append("请候选人解释空档期去向，并补充社保、项目或收入证明")
        elif risk["type"] == "频繁跳槽":
            focus.append("逐段确认离职原因，判断稳定性和岗位预期是否匹配")
        elif risk["type"] == "证书过期":
            focus.append("要求候选人提供最新证书编号或官方查询截图")
        elif risk["type"] == "技能存疑":
            focus.append("围绕声称熟练的核心技能追问真实项目、难点和个人贡献")
        elif risk["type"] == "信息存疑":
            focus.append("核实年限、项目规模和个人职责，要求候选人举证说明")

    match = candidate.get("match_result") or {}
    for gap in match.get("gap_points") or []:
        focus.append(f"针对匹配差距追问：{gap}")

    if not focus:
        focus = ["核实候选人在核心项目中的个人贡献", "确认入职动机、稳定性和薪资预期"]
    return list(dict.fromkeys(focus))[:6]


def _severity(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"high", "高", "严重"}:
        return "high"
    if text in {"medium", "中", "中等"}:
        return "medium"
    return "low"


def _parse_month(value: Any, ongoing_as_today: bool = False) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if ongoing_as_today and any(word in text for word in ("至今", "现在", "present", "current")):
        today = date.today()
        return _month_index(today.year, today.month)
    match = re.search(r"(20\d{2}|19\d{2})[.\-/年](1[0-2]|0?[1-9])", text)
    if not match:
        return None
    return _month_index(int(match.group(1)), int(match.group(2)))


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _year_month(index: int) -> tuple[int, int]:
    year = index // 12
    month = index % 12
    if month == 0:
        return year - 1, 12
    return year, month


def _months_between(start: int, end: int) -> int:
    return end - start


def _fmt_next_month(index: int) -> str:
    return _fmt_month(index + 1)


def _fmt_prev_month(index: int) -> str:
    return _fmt_month(index - 1)


def _fmt_month(index: int) -> str:
    year, month = _year_month(index)
    return f"{year}.{month:02d}"


def _fmt_months(months: int) -> str:
    years, rest = divmod(months, 12)
    if years and rest:
        return f"{years} 年 {rest} 个月"
    if years:
        return f"{years} 年"
    return f"{rest} 个月"
