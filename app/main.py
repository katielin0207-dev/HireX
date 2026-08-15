"""HireX 招聘甄选 AI 智能体统一入口。

比赛 MVP 按企业使用顺序保留三段主链路：
简历筛选（含 JD 与面试辅助）→ 人才评价 → 录用前风险核验。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ui.theme import inject_theme


st.set_page_config(
    page_title="HireX · 招聘甄选 AI 智能体",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_theme()


PAGES = [
    ("screening", "简历筛选", "app.views.screening_flow"),
    ("talent", "人才评价", "app.views.talent"),
    ("risk", "风险核验", "app.views.preoffer"),
]
PAGE_LABELS = {key: label for key, label, _ in PAGES}


def _render_unfinished_page(page_key: str) -> None:
    if page_key == "risk":
        title = "风险核验"
        owner = "B"
        reads = "简历解析结果、岗位要求"
        writes = "risk_report、状态 risk_checked"
    else:
        title = "面试辅助"
        owner = "B"
        reads = "匹配结果、风险报告、面试记录"
        writes = "interview_eval、状态 interviewed"

    st.header(title)
    st.info(f"{owner} 负责的页面尚未合并。对应文件到位后会自动替换本占位页。")
    left, right = st.columns(2)
    left.markdown(f"**读取上游数据**\n\n{reads}")
    right.markdown(f"**写入下游数据**\n\n{writes}")


def _render_page(page_key: str) -> None:
    module_path = next(path for key, _, path in PAGES if key == page_key)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            _render_unfinished_page(page_key)
            return
        raise

    render = getattr(module, "render", None)
    if not callable(render):
        st.error(f"页面模块 {module_path} 缺少 render() 入口。")
        return
    render()


pending_navigation = st.session_state.pop("_hirex_pending_navigation", None)
if pending_navigation in PAGE_LABELS:
    st.session_state["hirex_navigation"] = pending_navigation
if st.session_state.get("hirex_navigation") not in PAGE_LABELS:
    st.session_state["hirex_navigation"] = "screening"

st.markdown(
    """
    <div class="top-shell">
      <div class="top-brand">
        <span class="brand-mark">HX</span>
        <div><strong>HireX · 海信—招聘甄选智能体</strong><small>岗位千万条，匹配第一条。</small></div>
      </div>
      <div class="top-actions">
        <span class="mock-dot"></span><span>演示数据已连接</span>
        <b>AI管理后台</b>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
selected_page = st.radio(
    "主流程",
    options=[key for key, _, _ in PAGES],
    format_func=lambda key: PAGE_LABELS[key],
    horizontal=True,
    label_visibility="collapsed",
    key="hirex_navigation",
)
with st.container(border=True, key=f"hirex_workspace_{selected_page}"):
    _render_page(selected_page)
