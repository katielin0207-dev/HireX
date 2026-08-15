"""招聘风险识别：确定性规则负责硬风险，LLM只补充语义疑点。"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.shared import call_llm


def analyze_risk(candidate: dict, jd: dict | None = None, use_llm: bool = True) -> dict:
    parsed = candidate.get("resume_parsed") or {}
    raw = candidate.get("resume_text") or ""
    risks: list[dict] = []
    focus: list[str] = []

    gap_risks = _experience_gaps(parsed.get("experience") or [])
    risks.extend(gap_risks)
    if gap_risks:
        focus.append("请说明工作经历空档期的原因，并提供可验证的经历或证明。")

    jump_risk = _frequent_moves(parsed.get("experience") or [])
    if jump_risk:
        risks.append(jump_risk)
        focus.append("请逐段说明离职原因，并解释未来两到三年的职业规划。")

    cert_risks = _expired_certificates(raw)
    risks.extend(cert_risks)
    if cert_risks:
        focus.append("请提供相关证书编号、有效期或续证材料。")

    if use_llm and raw and "此处省略" not in raw:
        risks.extend(_semantic_risks(candidate, jd or {}))

    match = candidate.get("match_result") or {}
    for gap in (match.get("gap_points") or [])[:2]:
        focus.append(f"请用具体项目、个人动作和量化结果说明：{gap}")

    risks = _dedupe(risks)
    severities = [item.get("severity", "low") for item in risks]
    level = "高" if "high" in severities else "中" if "medium" in severities else "低"
    return {"level": level, "risks": risks, "interview_focus": _unique(focus)[:6]}


def _parse_month(value: str) -> date | None:
    if not value:
        return None
    if any(word in str(value) for word in ("至今", "现在", "present", "Present")):
        return date.today().replace(day=1)
    match = re.search(r"(19|20)\d{2}[./年-]?(\d{1,2})?", str(value))
    if not match:
        return None
    year = int(match.group(0)[:4])
    month_match = re.search(r"(?:19|20)\d{2}[./年-]?(\d{1,2})", match.group(0))
    month = int(month_match.group(1)) if month_match else 1
    return date(year, max(1, min(12, month)), 1)


def _month_delta(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _experience_gaps(experiences: list[dict]) -> list[dict]:
    periods = []
    for item in experiences:
        start, end = _parse_month(item.get("start", "")), _parse_month(item.get("end", ""))
        if start and end:
            periods.append((start, end, item))
    periods.sort(key=lambda row: row[0])
    risks = []
    for previous, current in zip(periods, periods[1:]):
        gap = _month_delta(previous[1], current[0]) - 1
        if gap < 6:
            continue
        severity = "high" if gap >= 12 else "medium"
        risks.append({
            "type": "经历断层",
            "severity": severity,
            "detail": f"相邻两段工作经历之间存在约{gap}个月空档，简历中未见充分说明。",
            "evidence": f"{previous[2].get('company', '上一段经历')}结束于{previous[2].get('end')}；"
                        f"{current[2].get('company', '下一段经历')}开始于{current[2].get('start')}。",
        })
    return risks


def _frequent_moves(experiences: list[dict]) -> dict | None:
    short_jobs = []
    for item in experiences:
        start, end = _parse_month(item.get("start", "")), _parse_month(item.get("end", ""))
        if start and end and 0 <= _month_delta(start, end) < 12:
            short_jobs.append(item)
    if len(short_jobs) < 2:
        return None
    companies = "、".join(item.get("company", "未命名公司") for item in short_jobs[:4])
    return {
        "type": "频繁跳槽",
        "severity": "medium",
        "detail": f"发现{len(short_jobs)}段不足一年的工作经历，需要核实稳定性。",
        "evidence": companies,
    }


def _expired_certificates(raw: str) -> list[dict]:
    risks = []
    current = datetime.now().date()
    pattern = re.compile(
        r"(?P<name>[A-Za-z0-9\u4e00-\u9fa5·\- ]{2,30}(?:证书|认证|资格证))[^\n]{0,40}?"
        r"(?:有效期|到期|截止)[:：]?\s*(?P<date>20\d{2}[./年-]\d{1,2}(?:[./月-]\d{1,2})?)"
    )
    for match in pattern.finditer(raw):
        text_date = match.group("date").replace("年", "-").replace("月", "-").replace(".", "-").replace("/", "-").rstrip("-")
        parts = [int(part) for part in text_date.split("-") if part]
        try:
            expiry = date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        except (ValueError, IndexError):
            continue
        if expiry < current:
            risks.append({
                "type": "证书过期",
                "severity": "high",
                "detail": f"{match.group('name').strip()}已超过简历注明的有效期。",
                "evidence": match.group(0).strip(),
            })
    return risks


def _semantic_risks(candidate: dict, jd: dict) -> list[dict]:
    prompt = f"""请只识别简历中的两类招聘疑点：信息前后矛盾、核心技能缺少项目成果佐证。
不得猜测，不得把未提供第三方背调数据描述成异常。每个判断必须引用简历原文。

岗位：{jd.get('title', '目标岗位')}
岗位要求：{jd.get('requirements', {})}
简历：{candidate.get('resume_text', '')[:5000]}

输出JSON：{{"risks":[{{"type":"信息存疑|技能存疑","severity":"medium|low","detail":"说明","evidence":"原文"}}]}}
没有证据时输出空数组。"""
    try:
        result = call_llm(prompt, system="你是严谨的企业招聘风险核验助手，只输出JSON。", expect_json=True)
    except Exception:
        return []
    items = result.get("risks", []) if isinstance(result, dict) else []
    return [item for item in items if isinstance(item, dict) and item.get("evidence")][:4]


def _dedupe(items: list[dict]) -> list[dict]:
    output, seen = [], set()
    for item in items:
        key = (str(item.get("type")), str(item.get("detail")))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))
