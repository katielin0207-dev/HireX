"""HireX 可复用展示组件。

只负责视觉，不读取或修改业务状态。四个模块共同使用，避免页面风格分叉。
"""

from __future__ import annotations

import streamlit as st

from .theme import score_color


def esc(value) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def page_header(title: str, subtitle: str = "", icon: str = "◆") -> None:
    st.markdown(
        f'<div class="pg-head"><div class="pg-icon">{esc(icon)}</div>'
        f'<div class="pg-main"><div class="pg-title">{esc(title)}</div>'
        + (f'<div class="pg-sub">{esc(subtitle)}</div>' if subtitle else "")
        + "</div></div>",
        unsafe_allow_html=True,
    )


def section(title: str, desc: str = "") -> None:
    st.markdown(
        f'<div class="sec-head"><span class="sec-title">{esc(title)}</span>'
        + (f'<span class="sec-desc">{esc(desc)}</span>' if desc else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="pill {esc(tone)}">{esc(text)}</span>'


def stat_grid(items: list[dict]) -> None:
    if not items:
        return
    cards = "".join(
        f'<div class="stat-card"><div class="sc-label">{esc(item.get("label"))}</div>'
        f'<div class="sc-value"'
        + (f' style="color:{esc(item["color"])}"' if item.get("color") else "")
        + f'>{esc(item.get("value"))}</div>'
        + (f'<div class="sc-hint">{esc(item["hint"])}</div>' if item.get("hint") else "")
        + "</div>"
        for item in items
    )
    st.markdown(
        f'<div class="stat-grid" style="grid-template-columns:repeat({len(items)},minmax(0,1fr))">'
        f"{cards}</div>",
        unsafe_allow_html=True,
    )


def evidence_list(
    items: list, tone: str = "neutral", icon: str = "•", empty_text: str = "暂无"
) -> None:
    if not items:
        st.caption(empty_text)
        return
    st.markdown(
        "".join(
            f'<div class="ev-item {esc(tone)}"><span class="ev-icon">{esc(icon)}</span>'
            f"<span>{esc(_point_text(item))}</span></div>"
            for item in items
        ),
        unsafe_allow_html=True,
    )


def score_bars(rows: list[tuple]) -> None:
    html = []
    for label, score in rows:
        color = score_color(score)
        try:
            width = max(0, min(100, float(score)))
        except (TypeError, ValueError):
            width = 0
        html.append(
            f'<div class="bar-row"><span class="br-label">{esc(label)}</span>'
            f'<div class="br-track"><div class="br-fill" style="width:{width}%;background:{color}"></div></div>'
            f'<span class="br-value" style="color:{color}">{esc(score)}</span></div>'
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def _point_text(item) -> str:
    if isinstance(item, dict):
        main = item.get("point") or item.get("reason") or item.get("description") or ""
        evidence = item.get("evidence") or item.get("quote") or ""
        return f"{main}（依据：{evidence}）" if evidence else str(main)
    return str(item)
