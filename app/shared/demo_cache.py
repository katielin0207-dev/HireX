"""演示模式缓存：演示翻车的保险。

原理：开发完成后 A 预跑一遍完整流程，把每个环节的输出存到
mock/demo_cache/{step}.json。演示时如果 DeepSeek API 挂了或超时，
页面检测到 DEMO_MODE=on 或 API 连续失败，直接读缓存展示。

开启方式（二选一）：
1. 环境变量 DEMO_MODE=on
2. 页面侧边栏开关（各视图读 demo_mode_enabled() 即可）

各模块接法（以 B 的简历筛选为例）：
    from app.shared import demo_mode_enabled, load_demo_cache

    if demo_mode_enabled():
        result = load_demo_cache("screening")   # 读缓存
    else:
        result = 实跑 LLM(...)
"""
import json
import os
from typing import Any, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(_BASE, "mock", "demo_cache")


def demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "").lower() in ("on", "1", "true")


def save_demo_cache(step: str, data: Any) -> None:
    """A 预跑时调用：save_demo_cache("screening", result)"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{step}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_demo_cache(step: str) -> Optional[Any]:
    """读某一步的缓存，不存在返回 None（调用方要兜底）。"""
    path = os.path.join(CACHE_DIR, f"{step}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
