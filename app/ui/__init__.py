"""视图层公共设施：设计 token（theme）与可复用组件（components）。

拆出来的原因：改造前 `main.py` 有 2156 行，一段 480 行的 <style> 和三份
复制粘贴的页头（各自内嵌同一张 5KB base64 logo）混在业务逻辑里 ——
改一次配色要在四个地方同步，实际结果是它们早就不一致了。
"""
from .theme import inject_theme, TOKENS, DIMENSION_COLORS, score_color, score_tone
from .components import (
    esc, page_header, section, stat_grid, score_bars, score_ring, verdict_banner,
    question_card, empty_state, kv_row, pill, evidence_list, progress_steps,
)

__all__ = [
    "inject_theme", "TOKENS", "DIMENSION_COLORS", "score_color", "score_tone",
    "esc", "page_header", "section", "stat_grid", "score_bars", "score_ring",
    "verdict_banner", "question_card", "empty_state", "kv_row", "pill",
    "evidence_list", "progress_steps",
]
