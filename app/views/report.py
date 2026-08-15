"""评估报告页。

★ 同样按「结论 → 依据 → 明细」收敛；另外修掉一处实际的显示问题：
  雷达图原来把网格线设成 #2d3245、刻度字设成 #9aa0b0 —— 那是给深色底
  配的颜色，而主题已经锁定亮色，于是深色网格压在白底上，刻度几乎看不清。
"""
import streamlit as st

from app.i18n import t
from app.ui import (
    empty_state, evidence_list, page_header, pill, progress_steps,
    score_color, score_ring, section, stat_grid, verdict_banner,
)

def _steps():
    return [t("step.upload"), t("step.analyze"), t("step.interview"), t("step.report")]

# ★ 这两张表原本是模块级常量、写死中文 —— 而模块级常量在 import 时求值，
#   语言切了也不会变。改成函数，每次渲染再取。
def _rec_text():
    return {k: t("rec." + k) for k in ("strong_hire", "hire", "hold", "no_hire")}


def _dim_labels():
    return {k: t("dim." + k) for k in
            ("job_match", "technical_ability", "communication",
             "comprehensive_quality", "integrity")}


def render() -> None:
    page_header(t("report.title"), t("report.subtitle"), "📊")

    if not st.session_state.get("interview_done"):
        progress_steps(_steps(), 2)
        empty_state(t("report.empty"), t("report.empty_desc"), "📊")
        return

    progress_steps(_steps(), 3)
    report = st.session_state.get("report_data")
    if not report:
        agent = st.session_state.get("interviewer")
        if agent and getattr(agent, "turns", None):
            with st.spinner(t("report.generating")):
                from app.reporter import generate_report
                report = generate_report(agent.get_interview_data())
                st.session_state.report_data = report
        else:
            st.warning(t("report.empty"))
            return
    if not report:
        return

    score = report.get("overall_score", report.get("calculated_score", 0))
    rec = report.get("recommendation", "")
    agent = st.session_state.get("interviewer")
    turns = len(agent.turns) if agent else 0

    # ── 结论 ────────────────────────────────────
    verdict_banner(
        score, _rec_text().get(rec, rec or "—"),
        report.get("summary") or report.get("overall_comment") or "",
        score_label=t("report.score"),
    )
    dim_scores = report.get("dimension_scores") or {}
    stat_grid([
        {"label": t("report.rounds"), "value": turns},
        {"label": t("report.dims"), "value": len(dim_scores)},
        {"label": t("report.highlights"), "value": len(report.get("highlights") or []),
         "color": score_color(90)},
        {"label": t("report.concerns"), "value": len(report.get("concerns") or []),
         "color": score_color(60)},
    ])

    # ── 依据：五维 ───────────────────────────────
    if dim_scores:
        section(t("report.five_dim"))
        col_ring, col_radar = st.columns([1, 2], gap="large")
        with col_ring:
            st.markdown(score_ring(score, 150, t("report.overall")), unsafe_allow_html=True)
            st.markdown("")
            for k, v in dim_scores.items():
                s = v.get("score", 0) if isinstance(v, dict) else v
                st.markdown(
                    f'<div class="kv"><span class="k">{_dim_labels().get(k, k)}</span>'
                    f'<span class="v" style="color:{score_color(s)}">{s}</span></div>',
                    unsafe_allow_html=True,
                )
        with col_radar:
            _render_radar(dim_scores)

    # ── 亮点 / 关注点 ────────────────────────────
    section(t("report.hl_and_cn"))
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(pill(t("report.highlights"), "success"), unsafe_allow_html=True)
        evidence_list(report.get("highlights") or [], "success", "★", t("report.no_hl"))
    with c2:
        st.markdown(pill(t("report.concerns"), "warning"), unsafe_allow_html=True)
        evidence_list(report.get("concerns") or [], "warning", "!", t("report.no_cn"))

    if report.get("contradictions"):
        st.markdown("")
        st.markdown(pill(t("report.contradict"), "danger"), unsafe_allow_html=True)
        evidence_list(report["contradictions"], "danger", "▲")

    # ── 逐题评审（折叠）──────────────────────────
    _render_question_review(report)


def _render_radar(dim_scores: dict) -> None:
    import plotly.graph_objects as go

    cats, vals = [], []
    for k, v in dim_scores.items():
        cats.append(_dim_labels().get(k, k))
        vals.append(v.get("score", 0) if isinstance(v, dict) else v)
    if not cats:
        return

    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]], theta=cats + [cats[0]],
        fill="toself", fillcolor="rgba(79,70,229,0.16)",
        line=dict(color="#4f46e5", width=2.5),
        marker=dict(color="#4f46e5", size=7),
        hovertemplate="%{theta}: %{r}<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            # ★ 亮色主题下的网格/刻度配色（原来是深色底的配色，白底上几乎看不清）
            radialaxis=dict(range=[0, 100], gridcolor="#e2e8f0", linecolor="#e2e8f0",
                            tickfont=dict(color="#94a3b8", size=10)),
            angularaxis=dict(gridcolor="#e2e8f0", linecolor="#cbd5e1",
                             tickfont=dict(color="#0f172a", size=12)),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=360, margin=dict(l=60, r=60, t=24, b=24), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_question_review(report: dict) -> None:
    q_review = report.get("question_review") or []
    agent = st.session_state.get("interviewer")
    if not q_review and agent:
        # ★ 循环变量原来叫 t —— 和翻译函数 t() 同名。推导式有自己的作用域所以
        #   眼下还能跑，但只要有人把它改成普通 for 循环，t() 就会被整个函数体
        #   遮蔽成一个 dict，报错点还离得很远。改名，不留这个雷。
        q_review = [{
            "round": turn.get("round", "?"),
            "question": turn.get("question", ""),
            "answer_summary": (turn.get("answer") or "")[:200],
            "score": (turn.get("evaluation") or {}).get("score", "—"),
            "evaluation": (turn.get("evaluation") or {}).get("answer_quality", ""),
        } for turn in agent.turns]
    if not q_review:
        return

    section(t("report.per_q"), t("report.q_count", n=len(q_review)))
    for r in q_review:
        sc = r.get("score", "—")
        tone = "neutral"
        if isinstance(sc, (int, float)) and sc > 0:
            tone = ("success" if sc >= 85 else "brand" if sc >= 70
                    else "warning" if sc >= 55 else "danger")
            sc = t("report.score_n", n=int(sc))
        title = (r.get("question") or "")[:60]
        with st.expander(t("report.round_n", n=r.get("round", "?")) + f" · {title}…"):
            st.markdown(pill(str(sc), tone), unsafe_allow_html=True)
            st.markdown(f'**{t("report.question")}**\n\n{r.get("question", "")}')
            st.markdown(f'**{t("report.answer")}**\n\n{r.get("answer_summary", "") or "—"}')
            if r.get("evaluation"):
                st.markdown(f'**{t("report.comment")}**\n\n{r["evaluation"]}')
