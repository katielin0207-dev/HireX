"""JD / 筛选相关的共享工具常量与函数。

由岗位投放页与简历筛选页共同使用，避免两个视图之间重复定义。
"""

# 四维权重字段（新契约）
_WEIGHT_DIMS = ["degree", "years", "skills", "soft"]
_DIM_LABEL = {"degree": "学历", "years": "相关经验", "skills": "必备技能", "soft": "软实力"}


_WEIGHT_TEMPLATE_RULES = {
    "campus": {
        "name": "校招 / 管培岗位模板",
        "ranges": {"degree": (20, 35), "years": (0, 10), "skills": (25, 40), "soft": (25, 40)},
        "tags": {"degree": "校招适用", "years": "潜力优先", "skills": "基础技能", "soft": "软实力偏高"},
    },
    "senior": {
        "name": "资深岗位模板",
        "ranges": {"degree": (5, 20), "years": (25, 40), "skills": (30, 45), "soft": (15, 30)},
        "tags": {"degree": "门槛参考", "years": "经验优先", "skills": "实战优先", "soft": "管理协作"},
    },
    "technical": {
        "name": "工程师 / 技术岗位模板",
        "ranges": {"degree": (10, 25), "years": (10, 25), "skills": (35, 50), "soft": (15, 30)},
        "tags": {"degree": "通用初始值", "years": "项目经验", "skills": "技术岗偏高", "soft": "通用能力"},
    },
    "manufacturing": {
        "name": "制造 / 质量实操岗位模板",
        "ranges": {"degree": (10, 20), "years": (20, 35), "skills": (35, 50), "soft": (15, 25)},
        "tags": {"degree": "实操岗适用", "years": "经验优先", "skills": "实操技能偏高", "soft": "跨部门协作"},
    },
    "functional": {
        "name": "职能岗位模板",
        "ranges": {"degree": (10, 25), "years": (15, 30), "skills": (25, 40), "soft": (20, 35)},
        "tags": {"degree": "通用初始值", "years": "相关经验", "skills": "岗位技能", "soft": "职能岗偏高"},
    },
}


def weight_template_for(job: dict) -> dict:
    """根据岗位场景返回默认模板、推荐区间和解释标签。"""
    title = str(job.get("title", ""))
    category = str(job.get("category", ""))
    level = str(job.get("level", ""))
    haystack = f"{title} {category} {level} {job.get('jd_text', '')}"

    if any(k in haystack for k in ("校招", "应届", "管培", "毕业生")):
        template_key = "campus"
    elif any(k in haystack for k in ("资深", "高级", "专家", "经理", "P7", "P8", "P9")):
        template_key = "senior"
    elif category in ("制造/工艺岗", "质量/IE 方向", "质量/IE方向"):
        template_key = "manufacturing"
    elif category == "工程师/技术岗":
        template_key = "technical"
    else:
        template_key = "functional"

    template = _WEIGHT_TEMPLATE_RULES[template_key]
    fallback = {"degree": .20, "years": .20, "skills": .35, "soft": .25}
    raw_defaults = job.get("recommended_weights") or fallback
    defaults = {
        dim: int(round(float(raw_defaults.get(dim, fallback[dim])) * 100))
        for dim in _WEIGHT_DIMS
    }
    # 历史岗位数据若有舍入误差，把差额补到技能项，保证默认即可直接使用。
    defaults["skills"] += 100 - sum(defaults.values())
    return {
        "key": template_key,
        "name": template["name"],
        "defaults": defaults,
        "ranges": template["ranges"],
        "tags": template["tags"],
    }


def weight_deviation_hint(dim: str, value: int, recommended_range: tuple[int, int]) -> tuple[str, str]:
    """返回权重偏离提示和提示等级（ok/warn）。"""
    low, high = recommended_range
    if low <= value <= high:
        return f"位于建议区间 {low}%–{high}%", "ok"

    if value > high:
        messages = {
            "degree": "学历占比偏高，更适合校招、管培或门槛型岗位；实操型岗位通常建议不超过 20%",
            "years": "经验占比偏高，可能减少高潜但年限较短候选人的机会",
            "skills": "技能占比偏高，适合技术、质量、工艺等强调实操的岗位",
            "soft": "软实力占比偏高，建议确保后续有结构化面试证据支撑",
        }
    else:
        messages = {
            "degree": "低于建议区间，请确认该岗位是否无需学历门槛",
            "years": "低于建议区间，请确认是否愿意接纳经验较少的高潜候选人",
            "skills": "低于建议区间，可能弱化岗位必备技能对结果的影响",
            "soft": "低于建议区间，可能弱化协作、沟通和问题解决能力的影响",
        }
    return messages[dim], "warn"


def validate_weight_total(raw: dict) -> tuple[int, bool, str]:
    """强校验四维权重总和，返回总和、是否合法和人类可读提示。"""
    total = sum(int(raw.get(dim, 0) or 0) for dim in _WEIGHT_DIMS)
    if total == 100:
        return total, True, "配置有效，可以开始筛选"
    if total < 100:
        return total, False, f"还差 {100 - total}%，请补足"
    return total, False, f"超出 {total - 100}%，请调低"

# 学历等级映射（用于硬性规则引擎）
_DEGREE_LEVEL = {"大专": 0, "本科": 1, "硕士": 2, "研究生": 2, "博士": 3, "博士后": 4}


def _normalize_weights(raw: dict) -> dict:
    """把四维权重（任意正数）归一化到和为 1。全零则退回均分。"""
    vals = {d: max(0.0, float(raw.get(d, 0) or 0)) for d in _WEIGHT_DIMS}
    total = sum(vals.values())
    if total <= 0:
        return {d: 1.0 / len(_WEIGHT_DIMS) for d in _WEIGHT_DIMS}
    return {d: v / total for d, v in vals.items()}


def _split_csv(s: str) -> list:
    """支持中/英文逗号分隔。"""
    return [x.strip() for x in (s or "").replace("，", ",").split(",") if x.strip()]


def _legacy_weights(jd: dict) -> bool:
    """检测旧 schema（hard/soft 二维权重）→ 需要用户重新保存。"""
    w = (jd or {}).get("weights", {}) or {}
    return "hard" in w and "degree" not in w
