"""共享公共件：LLM 调用 + 候选人存储 + 演示缓存

五个模块共用的基础设施，由 A 维护。其他人只用，不改。
用法见 docs/CONTRACT.md 第 5 节。
"""
from .llm import call_llm
from .parallel import map_llm
from .store import (
    save_candidate,
    load_candidate,
    update_candidate,
    list_candidates,
    save_jd,
    load_jd,
)
from .demo_cache import demo_mode_enabled, load_demo_cache, save_demo_cache

__all__ = [
    "call_llm",
    "map_llm",
    "save_candidate",
    "load_candidate",
    "update_candidate",
    "list_candidates",
    "save_jd",
    "load_jd",
    "demo_mode_enabled",
    "load_demo_cache",
    "save_demo_cache",
]
