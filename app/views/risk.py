"""风险核验页面：沿用B分支的结论先行、卡片化智能分析风格。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.risk_engine import analyze_risk
from app.shared import list_candidates, load_candidate, load_jd, update_candidate
from app.ui import esc, evidence_list, page_header, pill, score_color, section, stat_grid


LEVEL_TONE = {"低": "success", "中": "warning", "高": "danger", "未核验": "neutral"}


def render() -> None:
    _styles()
    page_header("智能分析", "批量比较候选人的匹配度、风险证据和下一步核验动作", "⚡")
    jd, candidates = load_jd(), list_candidates()
    if not jd or not candidates:
        st.warning("请先在简历筛选页完成岗位设置和候选人导入。")
        return

    rows = [_row(candidate) for candidate in candidates]
    top = sorted(rows, key=lambda row: row["匹配分"], reverse=True)[0]
    high = sum(row["风险等级"] == "高" for row in rows)
    pending = sum(row["风险等级"] == "未核验" for row in rows)
    st.markdown(
        f'<div class="analysis-hero"><div><span>岗位智能分析</span>'
        f'<h2>{esc(jd.get("title", "当前岗位"))}</h2>'
        f'<p>先看结论，再展开证据；风险只做前置预警，最终由HR和用人部门确认。</p></div>'
        f'<div class="analysis-best"><span>当前匹配首选</span><strong>{esc(top["姓名"])}</strong>'
        f'<small>{top["匹配分"]}分 · {esc(top["推荐动作"])}</small></div></div>',
        unsafe_allow_html=True,
    )
    stat_grid([
        {"label": "候选人", "value": len(rows), "hint": "本岗位人才池"},
        {"label": "建议推进", "value": sum(row["推荐动作"] == "建议推进" for row in rows), "color": "#059669"},
        {"label": "待核验", "value": pending, "color": "#d97706"},
        {"label": "高风险", "value": high, "color": "#dc2626"},
    ])

    left, right = st.columns([1, 1])
    with left:
        risk_filter = st.selectbox("风险筛选", ["全部", "高", "中", "低", "未核验"])
    with right:
        if st.button("批量规则扫描", type="primary", use_container_width=True):
            _batch_scan(candidates, jd)
            st.rerun()

    visible = [row for row in rows if risk_filter == "全部" or row["风险等级"] == risk_filter]
    section("候选人批量分析", "点击候选人查看风险依据和处理动作")
    if visible:
        st.dataframe(pd.DataFrame(visible), use_container_width=True, hide_index=True)
    else:
        st.info("当前筛选条件下没有候选人。")
        return

    ids = [row["id"] for row in visible]
    labels = {row["id"]: f'{row["姓名"]} · {row["匹配分"]}分 · {row["风险等级"]}风险' for row in visible}
    selected_id = st.selectbox("选择候选人查看详情", ids, format_func=lambda cid: labels[cid])
    candidate = load_candidate(selected_id) or {}
    _render_candidate(candidate, jd)


def _render_candidate(candidate: dict, jd: dict) -> None:
    match = candidate.get("match_result") or {}
    report = candidate.get("risk_report") or {}
    level = report.get("level", "未核验")
    st.markdown(
        f'<div class="candidate-command"><div><span>当前复核对象</span>'
        f'<h3>{esc(candidate.get("name", candidate.get("id")))}</h3>'
        f'<div>{pill(f"匹配 {match.get("overall_score", "—")}分", "brand")} '
        f'{pill(f"{level}风险", LEVEL_TONE.get(level, "neutral"))}</div></div>'
        f'<div class="candidate-summary">{esc(match.get("summary", "等待匹配结论"))}</div></div>',
        unsafe_allow_html=True,
    )

    a, b, c = st.columns([1, 1, 1])
    with a:
        use_llm = st.toggle("AI补充语义判断", value=True, help="规则识别时间线和证书；AI只补充有原文证据的疑点。")
    with b:
        if st.button("生成/刷新风险报告", type="primary", use_container_width=True):
            with st.status("正在形成风险报告...", expanded=True) as status:
                status.write("检查经历断层、跳槽频率和证书有效期")
                report = analyze_risk(candidate, jd, use_llm=use_llm)
                update_candidate(candidate["id"], "risk_report", report)
                update_candidate(candidate["id"], "status", "risk_checked")
                status.update(label="风险报告已生成", state="complete")
            st.rerun()
    with c:
        st.button(
            "生成候选人面试包",
            use_container_width=True,
            on_click=_go_interview,
            args=(candidate.get("id"),),
        )

    report = (load_candidate(candidate.get("id")) or candidate).get("risk_report") or {}
    if not report:
        st.info("尚未生成风险报告。点击上方按钮开始核验。")
        return
    risks = report.get("risks") or []
    level = report.get("level", "低")
    decision = "暂停推进，先完成关键核验" if level == "高" else "可推进，但面试必须带问题核验" if level == "中" else "风险可控，建议正常推进"
    color = {"高": "#dc2626", "中": "#d97706", "低": "#059669"}.get(level, "#64748b")
    st.markdown(
        f'<div class="risk-verdict" style="--risk:{color}"><div><span>HR处理建议</span>'
        f'<h2>{esc(decision)}</h2><p>共发现{len(risks)}个风险点；所有结论均需人工复核。</p></div>'
        f'<div class="risk-level" style="color:{color}">{esc(level)}<small>综合风险</small></div></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.2, 1])
    with left:
        section("风险证据")
        if not risks:
            st.success("未发现明显风险，建议继续核实核心项目贡献。")
        for index, risk in enumerate(risks, 1):
            tone = {"high": "danger", "medium": "warning", "low": "neutral"}.get(risk.get("severity"), "neutral")
            st.markdown(
                f'<div class="risk-card"><div><b>{index}. {esc(risk.get("type", "风险"))}</b>'
                f'{pill(risk.get("severity", "low"), tone)}</div>'
                f'<p>{esc(risk.get("detail", ""))}</p>'
                f'<small>证据：{esc(risk.get("evidence", "暂无"))}</small></div>',
                unsafe_allow_html=True,
            )
    with right:
        section("下一步核验清单")
        evidence_list(report.get("interview_focus") or [], "warning", "!", "暂无额外核验项")
        if st.button("模拟推送HR与用人部门", use_container_width=True):
            st.success("已生成核验待办（Demo）。正式接入后可回写招聘系统。")


def _row(candidate: dict) -> dict:
    match = candidate.get("match_result") or {}
    report = candidate.get("risk_report") or {}
    level = report.get("level", "未核验")
    score = int(match.get("overall_score", 0) or 0)
    action = "暂停核验" if level == "高" else "带问题推进" if level == "中" else "建议推进" if score >= 70 else "人工复核"
    return {
        "id": candidate.get("id"),
        "姓名": candidate.get("name", candidate.get("id")),
        "匹配分": score,
        "风险等级": level,
        "风险点": len(report.get("risks") or []),
        "推荐动作": action,
    }


def _batch_scan(candidates: list[dict], jd: dict) -> None:
    with st.status("正在批量扫描候选人...", expanded=True) as status:
        progress = st.progress(0)
        total = max(1, len(candidates))
        for index, candidate in enumerate(candidates, 1):
            status.write(f'扫描 {candidate.get("name", candidate.get("id"))}')
            report = analyze_risk(candidate, jd, use_llm=False)
            update_candidate(candidate["id"], "risk_report", report)
            update_candidate(candidate["id"], "status", "risk_checked")
            progress.progress(index / total)
        status.update(label="批量规则扫描完成", state="complete")


def _go_interview(candidate_id: str) -> None:
    st.session_state["selected_candidate_id"] = candidate_id
    st.session_state["hirex_navigation"] = "interview"


def _styles() -> None:
    st.markdown(
        """
        <style>
        .analysis-hero{display:grid;grid-template-columns:1fr 260px;gap:18px;background:#fff;border:1px solid var(--border);border-radius:14px;padding:18px;margin:6px 0 14px}.analysis-hero span,.candidate-command span,.risk-verdict span{font-size:12px;color:var(--text-3)}.analysis-hero h2,.candidate-command h3,.risk-verdict h2{color:var(--text);margin:4px 0}.analysis-hero p,.candidate-summary,.risk-verdict p{color:var(--text-2);font-size:13px}.analysis-best{background:var(--brand-50);border:1px solid var(--brand-100);border-radius:12px;padding:14px;display:flex;flex-direction:column;justify-content:center}.analysis-best strong{font-size:22px;color:var(--text);margin:4px 0}.analysis-best small{color:var(--text-2)}.candidate-command{display:flex;justify-content:space-between;align-items:center;gap:18px;background:#fff;border:1px solid var(--border);border-radius:14px;padding:17px;margin:14px 0}.candidate-summary{max-width:48%;text-align:right}.risk-verdict{display:grid;grid-template-columns:1fr 170px;align-items:center;background:#fff;border:1px solid var(--border);border-left:5px solid var(--risk);border-radius:14px;padding:18px;margin:18px 0}.risk-level{text-align:center;font-size:42px;font-weight:780}.risk-level small{display:block;font-size:12px;color:var(--text-3);font-weight:500}.risk-card{background:#fff;border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:10px}.risk-card>div{display:flex;justify-content:space-between;gap:10px}.risk-card b{color:var(--text)}.risk-card p{font-size:13px;color:var(--text-2)}.risk-card small{display:block;background:var(--surface-2);border-radius:8px;padding:9px;color:var(--text-2)}@media(max-width:900px){.analysis-hero,.risk-verdict{grid-template-columns:1fr}.candidate-command{display:block}.candidate-summary{max-width:none;text-align:left;margin-top:10px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
