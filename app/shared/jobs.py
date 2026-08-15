"""岗位（Job Positions）加载器。

现在从 mock/haixin_jobs.json 读示范数据；后续接入海信官网爬虫
只需替换 load_jobs() 的实现即可（保持返回结构一致）。

岗位分组按 category 字段（5 个固定分组，"高风险复核池" 是特殊池，
暂无常规岗位——UI 层做即将上线占位）。
"""
import json
import os
from typing import Optional

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


def load_jobs() -> list[dict]:
    """加载岗位列表。

    TODO(爬虫对接): 替换为 fetch_from_hisense_career_site()，
                    保持返回 dict 结构与 mock 一致即可无缝切换。
    """
    if not os.path.exists(_MOCK_JOBS_PATH):
        return []
    with open(_MOCK_JOBS_PATH, encoding="utf-8") as f:
        return json.load(f)


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
