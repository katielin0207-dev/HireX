"""简历分析页 —— 上传 / 分析 / 结果。

★ 信息架构改动（这是本次重构的核心，不是换配色）：

  改造前 `_show_analysis_results` 一个函数 260+ 行，把
  「四格统计 → 分数环 → 维度条 → 优势 → 差距 → 风险 → 题库 → 追问
    → 面试链接 → Checker → Graph → 飞轮」
  全部平铺展开，读的人要滚到底才知道"所以到底要不要这个人"。

  改造后按【结论 → 依据 → 明细 → 工程细节】四层收敛：
    第一屏  录用建议 + 匹配分 + 下一步动作
    第二屏  维度评分 + 优势/差距/风险（并排，不再上下堆）
    折叠区  题库（按维度分组）、模糊点追问
    折叠区  Checker / Graph / 飞轮（评审要看，候选人流程不关心）
"""
from collections import defaultdict

import streamlit as st

from app.config import settings
from app.parser import parse_uploaded_file
from app.i18n import t
from app.ui import (
    DIMENSION_COLORS, empty_state, evidence_list, kv_row, page_header, pill,
    progress_steps, question_card, score_bars, score_color, section, stat_grid,
    verdict_banner,
)

try:
    from app.integration import (
        render_checker_panel, render_flywheel_panel, render_graph_panel,
        run_analysis_with_pipeline,
    )
    NEW_ARCH = True
except Exception:      # noqa: BLE001
    NEW_ARCH = False

def _steps():
    """★ 每次渲染时才取翻译 —— 模块级常量会在 import 时定死语言，
    切换后不会跟着变（这是 i18n 最常见的一个坑）。"""
    return [t("step.upload"), t("step.analyze"), t("step.interview"), t("step.report")]

def _dim_labels():
    """同 report.py：模块级常量会在 import 时把语言定死，必须每次渲染再取。"""
    return {k: t("mdim." + k) for k in
            ("skills_match", "experience_match", "education_match", "project_relevance")}


def render() -> None:
    page_header(t("analysis.title"), t("analysis.subtitle"), "📄")
    if not st.session_state.get("analysis_done"):
        progress_steps(_steps(), 0)
        _render_upload()
    else:
        progress_steps(_steps(), 1)
        _render_results()


# ── 上传 ───────────────────────────────────────────────────────
def _render_upload() -> None:
    col_jd, col_cv = st.columns(2, gap="large")

    with col_jd:
        section(t("analysis.jd"), t("analysis.jd_hint"))
        jd_file = st.file_uploader(
            "上传 JD 文件", type=["pdf", "docx", "txt"], key="jd_upload",
            label_visibility="collapsed",
        )
        # ★ 原来这里是一个居中的「或」分隔符，渲染出来是个突兀的小方块。
        #   改成放在栏内的说明文字 —— 它本来就只对 JD 这一栏成立。
        jd_text_input = st.text_area(
            t("analysis.paste_label"), height=132, key="jd_text_input",
            placeholder=t("analysis.paste_hint"),
        )

    with col_cv:
        section(t("analysis.resume"), t("analysis.resume_hint"))
        resume_file = st.file_uploader(
            "上传简历文件", type=["pdf", "docx", "txt"], key="resume_upload",
            label_visibility="collapsed",
        )
        st.caption(t("analysis.sample_hint"))

    st.markdown("")
    ready = bool(resume_file) and bool(jd_file or (jd_text_input or "").strip())
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if st.button(t("analysis.start"), type="primary", use_container_width=True, disabled=not ready):
            run_analysis(jd_file, jd_text_input, resume_file)
        if not ready:
            st.caption(t("analysis.upload_ready_hint"))


def run_analysis(jd_file, jd_text_input, resume_file) -> None:
    with st.spinner(t("analysis.spinner_parse")):
        try:
            jd_text = ""
            if jd_file:
                jd_text = parse_uploaded_file(jd_file.read(), jd_file.name)
            elif (jd_text_input or "").strip():
                jd_text = jd_text_input.strip()
            resume_text = parse_uploaded_file(resume_file.read(), resume_file.name)
        except Exception as e:                        # noqa: BLE001
            # ★ 解析失败必须把原因说清楚。扫描件 PDF 是最常见的一种，
            #   笼统的"分析失败"会让人以为是模型或网络的问题。
            st.error(t("analysis.parse_failed") + str(e))
            return
        st.session_state.jd_text = jd_text
        st.session_state.resume_text = resume_text

    if not jd_text or not resume_text:
        st.error(t("analysis.empty_input"))
        return

    if NEW_ARCH:
        with st.spinner(t("analysis.spinner_run")):
            summary = run_analysis_with_pipeline(jd_text, resume_text)
        if summary.get("success"):
            st.session_state.analysis_done = True
            st.rerun()
        st.error(t("analysis.run_failed"))
        return

    # 旧链路兜底
    from app.matcher import run_match_pipeline
    from app.question_generator import run_question_pipeline
    with st.spinner("正在评估匹配度…"):
        pipe = run_match_pipeline(jd_text, resume_text)
        if not pipe.get("success"):
            st.error(f"分析失败：{pipe.get('error', '')}")
            return
        st.session_state.jd_data = pipe.get("jd_data", {})
        st.session_state.resume_data = pipe.get("resume_data", {})
        st.session_state.match_result = pipe.get("match_result", {})
    with st.spinner("正在生成面试题…"):
        qp = run_question_pipeline(
            jd_data=st.session_state.jd_data,
            resume_data=st.session_state.resume_data,
            match_result=st.session_state.match_result,
        )
        if not qp.get("success"):
            st.error(f"试题生成失败：{qp.get('error', '')}")
            return
        st.session_state.all_questions = qp.get("questions", {}).get("questions", [])
        st.session_state.ambiguity_followups = qp.get("ambiguity_followups", {})
        st.session_state.analysis_done = True
        st.rerun()


def reset_analysis() -> None:
    for k in ("analysis_done", "match_result", "all_questions", "ambiguity_followups",
              "jd_data", "resume_data", "jd_text", "resume_text",
              "interview_link_info", "selected_questions", "remaining_pool",
              "interview_started", "interviewer", "interview_done", "report_data",
              "tab_radio", "_nav_radio"):
        st.session_state.pop(k, None)
    st.rerun()


# ── 结果 ───────────────────────────────────────────────────────
def _render_results() -> None:
    match = st.session_state.get("match_result") or {}
    questions = st.session_state.get("all_questions") or []

    # 服务重启后 session 可能只剩半截，这种状态没法用，直接回上传页
    if not isinstance(match, dict) or "overall_score" not in match:
        reset_analysis()
        return
    if not questions:
        st.warning(t("analysis.session_lost"))
        reset_analysis()
        return

    score = match.get("overall_score", 0)
    jd_data = st.session_state.get("jd_data") or {}
    resume_data = st.session_state.get("resume_data") or {}

    # ── 第一屏：结论 ──────────────────────────────
    verdict_banner(
        score,
        match.get("recommendation", "—"),
        (match.get("recommendation_reason") or "")[:260],
    )
    stat_grid([
        {"label": t("analysis.target_role"), "value": jd_data.get("title") or "—"},
        {"label": t("analysis.candidate"), "value": resume_data.get("name") or "—"},
        {"label": t("analysis.questions"), "value": t("analysis.q_count", n=len(questions)),
         "hint": t("analysis.dim_cover", n=len({q.get("category") for q in questions}))},
        {"label": t("analysis.checker"),
         "value": t("analysis.checker_pass") if st.session_state.get("checker_passed") else t("analysis.checker_deg"),
         "color": score_color(100 if st.session_state.get("checker_passed") else 60),
         "hint": t("analysis.checker_rounds", n=len(st.session_state.get("checker_results", [])))},
    ])

    _render_next_actions(questions)

    # ── 第二屏：依据 ──────────────────────────────
    section(t("analysis.evidence"), t("analysis.evidence_hint"))
    col_score, col_ev = st.columns([1, 1.35], gap="large")
    with col_score:
        rows = [
            (_dim_labels().get(dim, dim), info.get("score", 0) if isinstance(info, dict) else info)
            for dim, info in (match.get("score_breakdown") or {}).items()
        ]
        if rows:
            score_bars(rows)
        else:
            st.caption(t("analysis.no_breakdown"))
    with col_ev:
        t_ok, t_gap, t_risk = st.tabs([
            f'{t("analysis.strengths")} {len(match.get("matched_points") or [])}',
            f'{t("analysis.gaps")} {len(match.get("gap_points") or [])}',
            f'{t("analysis.risks")} {len(match.get("risk_points") or [])}',
        ])
        with t_ok:
            evidence_list(match.get("matched_points") or [], "success", "✓", t("analysis.no_strengths"))
        with t_gap:
            evidence_list(match.get("gap_points") or [], "warning", "!", t("analysis.no_gaps"))
        with t_risk:
            evidence_list(match.get("risk_points") or [], "danger", "▲", t("analysis.no_risks"))

    # ── 明细（折叠）────────────────────────────────
    section(t("analysis.materials"))
    _render_question_bank(questions)
    _render_followups()

    # ── 工程细节（折叠）────────────────────────────
    if NEW_ARCH:
        section(t("analysis.engineering"), t("analysis.engineering_sub"))
        _render_engineering_panels()


def _render_next_actions(questions) -> None:
    """下一步动作紧跟结论 —— 看完建议就能直接操作，不用滚到页面底部。"""
    link_info = st.session_state.get("interview_link_info")
    st.markdown("")
    if link_info:
        st.success(f'{t("analysis.link_made")} · {link_info.get("jd_title", "")} · {t("analysis.link_expire")} {link_info.get("expires_at", "")}')
        st.code(link_info["link"], language=None)
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button(t("analysis.relink"), use_container_width=True):
                st.session_state.interview_link_info = None
                st.rerun()
        with c2:
            if st.button(t("analysis.self_test"), type="primary", use_container_width=True):
                _goto_interview(questions)
        with c3:
            if st.button(t("analysis.reset"), use_container_width=True):
                reset_analysis()
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button(t("analysis.make_link"), use_container_width=True, disabled=not questions,
                     help=t("analysis.make_link_help")):
            _make_link(questions)
    with c2:
        if st.button(t("analysis.self_test"), type="primary", use_container_width=True, disabled=not questions):
            _goto_interview(questions)
    with c3:
        if st.button(t("analysis.reset"), use_container_width=True):
            reset_analysis()


def _sample(questions):
    from app.question_sampler import sample_questions_for_interview
    return sample_questions_for_interview(questions, st.session_state.n_rounds)


def _make_link(questions) -> None:
    from app.interview_link import create_interview_link
    selected, remaining = _sample(questions)
    st.session_state.selected_questions = selected
    st.session_state.remaining_pool = remaining
    st.session_state.interview_started = True
    st.session_state.interview_link_info = create_interview_link(
        base_url=f"http://{settings.HOST}:{settings.PORT}",
        jd_title=st.session_state.jd_data.get("title", "岗位面试"),
        persona_name="AI面试官",
        max_rounds=len(selected) + 2,
        interview_config={
            "jd_data": st.session_state.jd_data,
            "resume_data": st.session_state.resume_data,
            "selected_questions": selected,
            "remaining_pool": remaining,
        },
    )
    st.rerun()


def _goto_interview(questions) -> None:
    if not st.session_state.get("selected_questions"):
        selected, remaining = _sample(questions)
        st.session_state.selected_questions = selected
        st.session_state.remaining_pool = remaining
    st.session_state.interview_started = True
    st.session_state.active_tab = "interview"
    st.session_state.pop("_nav_radio", None)
    st.rerun()


def _render_question_bank(questions) -> None:
    by_cat = defaultdict(list)
    for q in questions:
        by_cat[q.get("category", "未分类")].append(q)

    # 维度覆盖概览：一眼看出哪个维度题少
    chips = "".join(
        f'<span class="pill" style="color:{DIMENSION_COLORS.get(c, "#4f46e5")};'
        f'background:#fff;border-color:{DIMENSION_COLORS.get(c, "#4f46e5")}33;margin-right:6px">'
        f"{c} · {len(qs)}</span>"
        for c, qs in by_cat.items()
    )
    st.markdown(f'<div style="margin-bottom:10px">{chips}</div>', unsafe_allow_html=True)

    with st.expander(t("analysis.qbank", n=len(questions)), expanded=False):
        order = list(DIMENSION_COLORS.keys())
        cats = sorted(by_cat, key=lambda c: order.index(c) if c in order else 99)
        tabs = st.tabs([f"{c} ({len(by_cat[c])})" for c in cats])
        for tab, cat in zip(tabs, cats):
            with tab:
                st.markdown(
                    "".join(question_card(q, i + 1) for i, q in enumerate(by_cat[cat])),
                    unsafe_allow_html=True,
                )


def _render_followups() -> None:
    followups = st.session_state.get("ambiguity_followups") or {}
    groups = followups.get("followup_groups") or []
    if not groups:
        return
    sev_tone = {"high": "danger", "medium": "warning", "low": "success"}
    sev_text = {"high": "高危", "medium": "关注", "low": "低风险"}
    with st.expander(t("analysis.followups", n=len(groups)), expanded=False):
        for g in groups:
            sev = g.get("severity", "")
            st.markdown(
                pill(sev_text.get(sev, sev or "—"), sev_tone.get(sev, "neutral"))
                + f'  <b>{g.get("ambiguous_point", "")}</b>',
                unsafe_allow_html=True,
            )
            for fq in g.get("followups", []):
                st.markdown(f'- {fq.get("question", "")}')
                if fq.get("red_flag"):
                    st.caption("🚩 " + t("analysis.red_flag") + str(fq["red_flag"]))
            st.markdown("")


def _render_engineering_panels() -> None:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.expander("Checker 五维校准", expanded=False):
            results = st.session_state.get("checker_results") or []
            if results:
                render_checker_panel(results)
            else:
                st.caption("下次分析后显示")
    with c2:
        with st.expander("Graph DAG 执行状态", expanded=False):
            pipeline = st.session_state.get("_pipeline")
            if pipeline:
                render_graph_panel(pipeline)
            else:
                st.caption("分析完成后显示")
    with st.expander("飞轮统计（Loop 3 · RAG 进化）", expanded=False):
        render_flywheel_panel()
    used = st.session_state.get("skills_used") or []
    if used:
        st.markdown(
            "已激活 Skills：" + " ".join(pill(s, "brand") for s in used),
            unsafe_allow_html=True,
        )
