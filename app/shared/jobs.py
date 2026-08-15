"""岗位（Job Positions）加载器。

现在从 mock/haixin_jobs.json 读示范数据；后续接入海信官网爬虫
只需替换 load_jobs() 的实现即可（保持返回结构一致）。

岗位分组按 category 字段（5 个固定分组，"高风险复核池" 是特殊池，
暂无常规岗位——UI 层做即将上线占位）。
"""
import json
import os
from typing import Optional

from .store import load_jd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MOCK_JOBS_PATH = os.path.join(_ROOT, "mock", "haixin_jobs.json")

# 岗位范围（固定 5 个）
JOB_CATEGORIES = [
    "工程师/技术岗",
    "制造/工艺岗",
    "质量/IE 方向",
    "职能/非技术岗",
    "高风险复核池",
]


def _published_job() -> Optional[dict]:
    """把岗位投放页发布的 JD 转成筛选模块通用的岗位结构。"""
    jd = load_jd() or {}
    req = jd.get("requirements") or {}
    hard = req.get("hard") or {}
    basics = jd.get("basics") or {}
    title = basics.get("position") or req.get("title") or jd.get("title")
    if not title or not hard:
        return None

    signal = " ".join([
        str(title),
        str(basics.get("dept", "")),
        " ".join(hard.get("must_skills") or []),
    ]).lower()
    if any(x in signal for x in ("质量", "ie", "8d", "spc", "fmea")):
        category = "质量/IE 方向"
    elif any(x in signal for x in ("制造", "工艺", "生产", "smt")):
        category = "制造/工艺岗"
    elif any(x in signal for x in ("工程师", "开发", "算法", "技术", "python")):
        category = "工程师/技术岗"
    else:
        category = "职能/非技术岗"

    return {
        "id": "published_jd",
        "category": category,
        "title": title,
        "dept": basics.get("dept", ""),
        "location": basics.get("location", ""),
        "level": basics.get("level", ""),
        "count": int(basics.get("count", 1) or 1),
        "source_url": "北森岗位需求（演示）",
        "hard": hard,
        "soft": req.get("soft") or [],
        "recommended_weights": jd.get("weights") or {
            "degree": 0.15, "years": 0.20, "skills": 0.40, "soft": 0.25,
        },
        "recommended_thresholds": jd.get("thresholds") or {"pass": 80, "hold": 60},
        "jd_text": jd.get("jd_text_generated") or jd.get("raw_text") or "",
        "published": True,
    }


def load_jobs() -> list[dict]:
    """加载岗位列表。

    TODO(爬虫对接): 替换为 fetch_from_hisense_career_site()，
                    保持返回 dict 结构与 mock 一致即可无缝切换。
    """
    jobs = []
    if os.path.exists(_MOCK_JOBS_PATH):
        with open(_MOCK_JOBS_PATH, encoding="utf-8") as f:
            jobs = json.load(f)
    published = _published_job()
    if published:
        jobs = [published] + [job for job in jobs if job.get("id") != published["id"]]
    return jobs


def load_job(job_id: str) -> Optional[dict]:
    for j in load_jobs():
        if j.get("id") == job_id:
            return j
    return None


def group_jobs_by_category(jobs: list[dict]) -> dict[str, list[dict]]:
    """按 category 分组，返回 {category: [job,...]}；顺序按 JOB_CATEGORIES。"""
    grouped: dict[str, list[dict]] = {c: [] for c in JOB_CATEGORIES}
    for j in jobs:
        cat = j.get("category") or "职能/非技术岗"
        grouped.setdefault(cat, []).append(j)
    return grouped


def jobs_in_category(category: str) -> list[dict]:
    return [j for j in load_jobs() if j.get("category") == category]
