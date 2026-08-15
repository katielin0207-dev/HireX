"""可复用视图组件。

组件只负责"长什么样"，不碰 session_state、不做业务判断 —— 这样
三个页面才能真正共用一套外观，而不是各自复制一份 HTML 再慢慢长歪。
"""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

from .theme import TOKENS, DIMENSION_COLORS, score_color, score_tone

_ROOT = Path(__file__).resolve().parents[2]


def esc(s) -> str:
    """最小转义。组件全部走 unsafe_allow_html，用户/模型产出的文本
    必须先过这里，否则一个 `<` 就能把版面拆了。"""
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """★ 从 logo.png 读一次并缓存。

    改造前：同一段 5KB 的 base64 被【原样复制粘贴了三份】写死在三个页头里
    （main.py 的 1217 / 1600 / 1869 行），源码里 15KB 全是同一张图。
    换 logo 要改三处，而且三处早晚会不一致。
    """
    for name in ("logo.png", "assets/logo.png"):
        p = _ROOT / name
        if p.exists():
            return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
    return ""


# ── 页头 ───────────────────────────────────────────────────────
def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """页头。三个页面共用一个 —— 这是本次拆分最直接的收益。"""
    logo = _logo_data_uri()
    if logo:
        badge = (f'<div class="pg-icon" style="background:#fff;border:1px solid var(--border)">'
                 f'<img src="{logo}" style="width:26px;height:auto" alt=""></div>')
    else:
        badge = f'<div class="pg-icon">{esc(icon) or "◆"}</div>'
    st.markdown(
        f'<div class="pg-head">{badge}<div class="pg-main">'
        f'<div class="pg-title">{esc(title)}</div>'
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


# ── 结论先行 ───────────────────────────────────────────────────
def verdict_banner(score, verdict: str, reason: str = "", score_label: str = "综合匹配度") -> None:
    """结论横幅。

    ★ 信息架构的核心改动：改造前结果页是"分数环 → 四个维度条 → 优势 →
      差距 → 风险 → 题库 → 追问"一路平铺 260+ 行，读的人要滚到底才知道
      "所以到底要不要这个人"。现在**结论和建议放在第一屏**，证据与明细
      折叠在下面按需展开。
    """
    tone = score_tone(score)
    color = score_color(score)
    st.markdown(
        f'<div class="verdict">'
        f'<div class="v-bar" style="background:{color}"></div>'
        f'<div class="v-main">'
        f'<div class="v-label">录用建议</div>'
        f'<div class="v-text" style="color:{color}">{esc(verdict) or "—"}</div>'
        + (f'<div class="v-why">{esc(reason)}</div>' if reason else "")
        + "</div>"
        f'<div class="v-score">'
        f'<div class="v-num" style="color:{color}">{esc(score)}</div>'
        f'<div class="v-unit">{esc(score_label)}</div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ── 指标 ───────────────────────────────────────────────────────
def stat_grid(items: list[dict]) -> None:
    """items: [{label, value, hint?, color?}]"""
    if not items:
        return
    cards = "".join(
        f'<div class="stat-card">'
        f'<div class="sc-label">{esc(it.get("label"))}</div>'
        f'<div class="sc-value"'
        + (f' style="color:{it["color"]}"' if it.get("color") else "")
        + f'>{esc(it.get("value"))}</div>'
        + (f'<div class="sc-hint">{esc(it["hint"])}</div>' if it.get("hint") else "")
        + "</div>"
        for it in items
    )
    st.markdown(
        f'<div class="stat-grid" style="grid-template-columns:repeat({len(items)},minmax(0,1fr))">'
        f"{cards}</div>",
        unsafe_allow_html=True,
    )


def score_bars(rows: list[tuple]) -> None:
    """rows: [(label, score)] —— 维度评分条"""
    html = []
    for label, s in rows:
        c = score_color(s)
        try:
            w = max(0, min(100, float(s)))
        except (TypeError, ValueError):
            w = 0
        html.append(
            f'<div class="bar-row"><span class="br-label">{esc(label)}</span>'
            f'<div class="br-track"><div class="br-fill" style="width:{w}%;background:{c}"></div></div>'
            f'<span class="br-value" style="color:{c}">{esc(s)}</span></div>'
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def kv_row(pairs: list[tuple]) -> None:
    st.markdown(
        "".join(
            f'<div class="kv"><span class="k">{esc(k)}</span><span class="v">{esc(v)}</span></div>'
            for k, v in pairs
        ),
        unsafe_allow_html=True,
    )


def score_ring(score, size: int = 132, caption: str = "") -> str:
    """返回 HTML 字符串（调用方自行 st.markdown）"""
    c = score_color(score)
    stroke = 9
    r = (size - stroke) // 2
    circ = 2 * 3.14159265 * r
    try:
        pct = max(0.0, min(1.0, float(score) / 100))
    except (TypeError, ValueError):
        pct = 0.0
    return (
        f'<div class="ring-wrap" style="width:{size}px;height:{size}px">'
        f'<svg width="{size}" height="{size}" style="transform:rotate(-90deg)">'
        f'<circle cx="{size//2}" cy="{size//2}" r="{r}" fill="none" '
        f'stroke="{TOKENS["surface-3"]}" stroke-width="{stroke}"/>'
        f'<circle cx="{size//2}" cy="{size//2}" r="{r}" fill="none" stroke="{c}" '
        f'stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-dasharray="{circ*pct:.1f} {circ:.1f}"/></svg>'
        f'<div class="ring-val" style="color:{c};font-size:{size//3.6:.0f}px">{esc(score)}'
        + (f'<span class="ring-cap">{esc(caption)}</span>' if caption else "")
        + "</div></div>"
    )


# ── 徽标 / 证据 ────────────────────────────────────────────────
def pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="pill {tone}">{esc(text)}</span>'


def evidence_list(items: list, tone: str = "neutral", icon: str = "•",
                  empty_text: str = "暂无") -> None:
    if not items:
        st.caption(empty_text)
        return
    st.markdown(
        "".join(
            f'<div class="ev-item {tone}"><span class="ev-icon">{icon}</span>'
            f"<span>{esc(_point_text(p))}</span></div>"
            for p in items
        ),
        unsafe_allow_html=True,
    )


def _point_text(p) -> str:
    """匹配理由既可能是字符串，也可能是 {point/reason/evidence} 字典 ——
    两种都出现过，这里统一。"""
    if isinstance(p, dict):
        main = p.get("point") or p.get("reason") or p.get("description") or ""
        ev = p.get("evidence") or p.get("quote") or ""
        return f"{main}（原文：{ev}）" if ev else str(main)
    return str(p)


# ── 题卡 ───────────────────────────────────────────────────────
_DIFF_TONE = {"简单": "success", "中等": "warning", "困难": "danger"}


def question_card(q: dict, index: int = None) -> str:
    cat = q.get("category", "未分类")
    diff = q.get("difficulty", "")
    color = DIMENSION_COLORS.get(cat, TOKENS["brand"])
    num = f'<span style="color:var(--text-3);font-weight:600">{index}.</span> ' if index else ""
    metas = [pill(cat, "brand")]
    if diff:
        metas.append(pill(f"难度 {diff}", _DIFF_TONE.get(diff, "neutral")))
    if q.get("time_minutes"):
        metas.append(pill(f'{q["time_minutes"]} 分钟', "neutral"))
    intent = q.get("intent") or q.get("assessment_point") or ""
    criteria = q.get("scoring_criteria") or q.get("criteria") or ""
    body = ""
    if intent:
        body += f"<b>考察点：</b>{esc(intent)}"
    if criteria:
        body += ("<br>" if body else "") + f"<b>评分标准：</b>{esc(criteria if isinstance(criteria, str) else '、'.join(map(str, criteria)))}"
    return (
        f'<div class="q-card" style="border-left-color:{color}">'
        f'<div class="q-text">{num}{esc(q.get("question", ""))}</div>'
        f'<div class="q-meta">{"".join(metas)}</div>'
        + (f'<div class="q-intent">{body}</div>' if body else "")
        + "</div>"
    )


# ── 空状态 / 步骤条 ────────────────────────────────────────────
def empty_state(title: str, desc: str = "", icon: str = "📄") -> None:
    st.markdown(
        f'<div class="empty"><div class="em-icon">{esc(icon)}</div>'
        f'<div class="em-title">{esc(title)}</div>'
        + (f'<div class="em-desc">{esc(desc)}</div>' if desc else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def progress_steps(steps: list[str], current: int) -> None:
    """current 为 0-based 索引；小于它的算已完成。"""
    parts = []
    for i, s in enumerate(steps):
        cls = "done" if i < current else ("active" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        parts.append(f'<div class="stp {cls}"><span class="dot">{mark}</span>{esc(s)}</div>')
        if i < len(steps) - 1:
            parts.append('<div class="link"></div>')
    st.markdown(f'<div class="steps">{"".join(parts)}</div>', unsafe_allow_html=True)
