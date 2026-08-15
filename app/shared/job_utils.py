"""JD / 筛选相关的共享工具常量与函数。

由岗位投放页与简历筛选页共同使用，避免两个视图之间重复定义。
"""

# 四维权重字段（新契约）
_WEIGHT_DIMS = ["degree", "years", "skills", "soft"]
_DIM_LABEL = {"degree": "学历", "years": "年限", "skills": "必备技能", "soft": "软实力"}

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
