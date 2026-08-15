"""HireX 统一视觉主题与展示组件。"""
from .theme import inject_theme, TOKENS, DIMENSION_COLORS, score_color, score_tone
from .components import esc, page_header, section, pill, stat_grid, evidence_list, score_bars

__all__ = [
    "inject_theme", "TOKENS", "DIMENSION_COLORS", "score_color", "score_tone",
    "esc", "page_header", "section", "pill", "stat_grid", "evidence_list", "score_bars",
]
