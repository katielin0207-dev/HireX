"""B module page: risk identification and qualification checks."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.risk_engine import analyze_risk
from app.shared import list_candidates, load_candidate, load_jd, update_candidate
from app.ui import esc, page_header, pill, score_color, section


_LEVEL_TONE = {"低": "success", "中": "warning", "高": "danger"}
_SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}
_SEVERITY_COLOR = {"high": "#dc2626", "medium": "#d97706", "low": "#059669"}
_TYPE_LABELS = ["经历断层", "频繁跳槽", "证书过期", "信息存疑", "技能存疑", "背调异常"]


def render() -> None:
    _inject_risk_styles()
    page_header("智能分析", "批量比较候选人的匹配度、风险等级和下一步推进建议", "⚡")

    jd = load_jd()
    candidates = list_candidates()
    if not jd or not candidates:
        st.warning("请先生成 Mock 数据，或让 A 在简历筛选页导入候选人。")
        return

    selected_id = _render_batch_dashboard(jd, candidates)
    candidate = load_candidate(selected_id)
    if not candidate:
        st.error("候选人数据不存在，请刷新后重试。")
        return

    _render_command_bar(candidate, jd, selected_id)

    st.divider()
    candidate = load_candidate(selected_id) or candidate
    _render_report(candidate)
    _render_raw(candidate)


def _candidate_selector(candidates: list[dict]) -> str:
    options = [c["id"] for c in candidates if c.get("id")]
    names = {c["id"]: c.get("name", c["id"]) for c in candidates}
    return st.selectbox("选择候选人", options=options, format_func=lambda cid: f"{names[cid]} · {cid}")


def _render_batch_dashboard(jd: dict, candidates: list[dict]) -> str:
    rows = _candidate_rows(candidates)
    selected_default = st.session_state.get("risk_selected_candidate")
    if selected_default not in {r["id"] for r in rows}:
        selected_default = rows[0]["id"] if rows else ""

    top = _best_candidate(rows)
    total = len(rows)
    proceed_count = sum(1 for r in rows if r["推荐动作"] in ("优先推进", "进入AI面试"))
    verify_count = sum(1 for r in rows if "核验" in r["推荐动作"] or r["风险等级"] == "中")
    high_count = sum(1 for r in rows if r["风险等级"] == "高")
    bg = _batch_background_stats(candidates)

    st.markdown(
        f"""
        <div class="batch-hero">
          <div>
            <div class="risk-eyebrow">岗位智能分析</div>
            <div class="batch-title">{esc(jd.get("title", "当前岗位"))}</div>
            <div class="batch-sub">先批量排序，再点选候选人查看风险证据和面试核验动作。</div>
          </div>
          <div class="batch-best">
            <span>当前首选</span>
            <strong>{esc(top.get("姓名", "—"))}</strong>
            <small>{esc(top.get("推荐理由", "等待候选人数据"))}</small>
          </div>
        </div>
        <div class="risk-kpi-grid">
          <div class="risk-kpi"><span class="risk-kpi-label">候选人</span><strong>{total}</strong><small>本岗位人才池</small></div>
          <div class="risk-kpi"><span class="risk-kpi-label">建议推进</span><strong class="risk-level-低">{proceed_count}</strong><small>可直接进入面试</small></div>
          <div class="risk-kpi"><span class="risk-kpi-label">待核验</span><strong class="risk-level-中">{verify_count}</strong><small>带问题推进</small></div>
          <div class="risk-kpi"><span class="risk-kpi-label">高风险</span><strong class="risk-level-高">{high_count}</strong><small>先暂停核验</small></div>
        </div>
        <div class="batch-bg-strip">
          <div>
            <span class="risk-eyebrow">背调报告概览</span>
            <strong>{bg["ready"]}/{total} 已形成核验摘要</strong>
            <small>覆盖身份、犯罪/社会安全、吸毒、网贷、诉讼、商业关联、学历学位</small>
          </div>
          <div class="batch-bg-states">
            {pill(f'{bg["abnormal"]} 异常', "danger" if bg["abnormal"] else "success")}
            {pill(f'{bg["pending"]} 待核验', "warning" if bg["pending"] else "neutral")}
            {pill(f'{bg["clear"]} 正常', "success")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([1.1, 1, 1, 1], gap="medium")
    with c1:
        sort_by = st.selectbox("排序", ["综合推荐", "匹配分最高", "风险最高", "待核验优先"], label_visibility="collapsed")
    with c2:
        risk_filter = st.selectbox("风险", ["全部风险", "高", "中", "低", "未核验"], label_visibility="collapsed")
    with c3:
        action_filter = st.selectbox("动作", ["全部动作", "优先推进", "进入AI面试", "先核验", "暂不推进"], label_visibility="collapsed")
    with c4:
        if st.button("批量规则扫描", use_container_width=True):
            with st.status("正在批量扫描候选人风险...", expanded=True) as status:
                total_items = max(1, len(candidates))
                progress = st.progress(0)
                for idx, cand in enumerate(candidates, start=1):
                    status.write(f"扫描 {cand.get('name', cand.get('id'))}")
                    report = analyze_risk(cand, jd, use_llm=False)
                    update_candidate(cand["id"], "risk_report", report)
                    progress.progress(idx / total_items)
                status.update(label="批量扫描完成", state="complete")
            st.rerun()

    filtered = _sort_rows(_filter_rows(rows, risk_filter, action_filter), sort_by)
    _render_batch_table(filtered, candidates, jd)

    ids = [r["id"] for r in filtered] or [r["id"] for r in rows]
    labels = {r["id"]: f'{r["姓名"]} · {r["匹配分"]}分 · {r["风险等级"]}风险 · {r["推荐动作"]}' for r in rows}
    index = ids.index(selected_default) if selected_default in ids else 0
    selected_id = st.selectbox(
        "选择候选人查看详情",
        options=ids,
        index=index,
        format_func=lambda cid: labels.get(cid, cid),
    )
    st.session_state["risk_selected_candidate"] = selected_id
    return selected_id


def _render_batch_table(rows: list[dict], candidates: list[dict], jd: dict) -> None:
    if not rows:
        st.info("当前筛选条件下没有候选人。")
        return
    candidate_map = {c.get("id"): c for c in candidates}
    st.markdown('<div class="candidate-list-head">候选人批量分析</div>', unsafe_allow_html=True)
    for row in rows:
        cid = row["id"]
        level = row["风险等级"]
        level_tone = _LEVEL_TONE.get(level, "neutral")
        action_tone = _action_tone(row["推荐动作"])
        with st.container():
            st.markdown(
                f"""
                <div class="candidate-row">
                  <div class="candidate-main">
                    <div class="candidate-name">{esc(row["姓名"])}</div>
                    <div class="candidate-reason">{esc(row["推荐理由"])}</div>
                    <div class="candidate-tags">
                      {pill(f'{row["匹配分"]}分', "brand")}
                      {pill(f'{level}风险', level_tone)}
                      {pill(row["推荐动作"], action_tone)}
                      {''.join(pill(t.strip(), "neutral") for t in row["关键标签"].split("/")[:2] if t.strip() and t.strip() != "暂无")}
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_view, col_interview, col_refresh = st.columns([1, 1, 1], gap="small")
            with col_view:
                if st.button("查看详情", key=f"view_{cid}", use_container_width=True):
                    st.session_state["risk_selected_candidate"] = cid
                    st.rerun()
            with col_interview:
                if st.button("进入 AI 面试", key=f"interview_{cid}", use_container_width=True):
                    st.session_state["selected_candidate_id"] = cid
                    st.session_state["risk_selected_candidate"] = cid
                    st.session_state["active_tab"] = "interview_eval"
                    st.session_state["_nav_radio"] = "interview_eval"
                    st.rerun()
            with col_refresh:
                if st.button("复核风险", key=f"refresh_{cid}", use_container_width=True):
                    candidate = candidate_map.get(cid)
                    if candidate:
                        report = analyze_risk(candidate, jd, use_llm=False)
                        update_candidate(cid, "risk_report", report)
                        update_candidate(cid, "status", "risk_checked")
                        st.session_state["risk_selected_candidate"] = cid
                        st.rerun()


def _render_command_bar(candidate: dict, jd: dict, selected_id: str) -> None:
    match = candidate.get("match_result") or {}
    tags = candidate.get("tags") or []
    report = candidate.get("risk_report") or {}
    level = report.get("level", "未核验")
    level_tone = _LEVEL_TONE.get(level, "neutral")
    st.markdown(
        f"""
        <div class="risk-command">
          <div>
            <div class="risk-eyebrow">当前复核对象</div>
            <div class="risk-name">{esc(candidate.get("name", selected_id))}</div>
            <div class="risk-meta">
              <span>匹配分 <b style="color:{score_color(match.get("overall_score", 0))}">{esc(match.get("overall_score", "—"))}</b></span>
              <span>状态 {esc(candidate.get("status", "new"))}</span>
              <span>风险 {pill(level, level_tone)}</span>
            </div>
          </div>
          <div class="risk-tags">
            {"".join(pill(tag, "neutral") for tag in tags[:5])}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_a, col_b, col_c, col_d = st.columns([1, 1, 1, 1.2], gap="medium")
    with col_a:
        use_llm = st.toggle("AI 补充判断", value=True, help="规则识别硬风险；AI 补充信息存疑和技能真实性。")
    with col_b:
        if st.button("生成/刷新风险报告", type="primary", use_container_width=True):
            with st.status("正在生成 HR 风险摘要...", expanded=True) as status:
                st.write("扫描简历时间线、证书有效期、任职稳定性")
                report = analyze_risk(candidate, jd, use_llm=use_llm)
                status.update(label="写入候选人风险字段", state="running")
                update_candidate(selected_id, "risk_report", report)
                update_candidate(selected_id, "status", "risk_checked")
                status.update(label="风险报告已生成", state="complete")
            st.rerun()
    with col_c:
        if st.button("进入 AI 面试", use_container_width=True):
            st.session_state["selected_candidate_id"] = selected_id
            st.session_state["risk_selected_candidate"] = selected_id
            st.session_state["active_tab"] = "interview_eval"
            st.session_state["_nav_radio"] = "interview_eval"
            st.rerun()
    with col_d:
        st.caption("HR 使用建议：先看顶部结论，再处理右侧核验清单。证据明细只在需要复核时展开。")


def _render_report(candidate: dict) -> None:
    report = candidate.get("risk_report")
    if not report:
        _render_empty_report()
        return

    match = candidate.get("match_result") or {}
    level = report.get("level", "低")
    risks = report.get("risks") or []
    decision = _decision_for(level, risks, match)
    distribution = _risk_distribution(risks)

    _render_decision_banner(level, risks, decision)
    _render_hr_overview(level, risks, distribution, candidate)
    _render_background_check(candidate, risks, compact=True)
    _render_risk_closure(candidate, level, risks, report.get("interview_focus") or [], decision)

    col_left, col_right = st.columns([1.25, 1], gap="large")
    with col_left:
        _render_risk_cards(risks)
    with col_right:
        _render_verification_actions(report.get("interview_focus") or [], level)

    _render_detail_table(risks)


def _render_empty_report() -> None:
    st.markdown(
        """
        <div class="risk-empty">
          <div class="risk-empty-icon">!</div>
          <div>
            <div class="risk-empty-title">还没有风险报告</div>
            <div class="risk-empty-text">HR 进入候选人复核时，先点击“生成/刷新风险报告”。系统会把简历疑点整理为风险等级、证据和下一步核验动作。</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision_banner(level: str, risks: list[dict], decision: dict) -> None:
    color = {"低": "#059669", "中": "#d97706", "高": "#dc2626"}.get(level, "#64748b")
    progress = {"低": 24, "中": 58, "高": 88}.get(level, 10)
    high_count = sum(1 for r in risks if r.get("severity") == "high")
    st.markdown(
        f"""
        <div class="risk-decision" style="--risk-color:{color};--risk-progress:{progress}%">
          <div class="risk-decision-main">
            <div class="risk-eyebrow">HR 处理建议</div>
            <div class="risk-decision-title">{esc(decision["title"])}</div>
            <div class="risk-decision-copy">{esc(decision["copy"])}</div>
            <div class="risk-action-row">
              <span>{pill(decision["owner"], "brand")}</span>
              <span>{pill(decision["sla"], "neutral")}</span>
              <span>{pill(f"{high_count} 个高风险项", "danger" if high_count else "success")}</span>
            </div>
          </div>
          <div class="risk-meter">
            <div class="risk-meter-label">综合风险</div>
            <div class="risk-meter-value" style="color:{color}">{esc(level)}</div>
            <div class="risk-meter-track"><div class="risk-meter-fill"></div></div>
            <div class="risk-meter-scale"><span>可推进</span><span>需核验</span><span>暂停</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hr_overview(level: str, risks: list[dict], distribution: dict, candidate: dict) -> None:
    match = candidate.get("match_result") or {}
    high_count = sum(1 for r in risks if r.get("severity") == "high")
    medium_count = sum(1 for r in risks if r.get("severity") == "medium")
    low_count = sum(1 for r in risks if r.get("severity") == "low")
    st.markdown(
        f"""
        <div class="risk-kpi-grid">
          <div class="risk-kpi">
            <span class="risk-kpi-label">匹配分</span>
            <strong style="color:{score_color(match.get("overall_score", 0))}">{esc(match.get("overall_score", "—"))}</strong>
            <small>{esc(match.get("recommendation", "筛选结论待确认"))}</small>
          </div>
          <div class="risk-kpi">
            <span class="risk-kpi-label">风险等级</span>
            <strong class="risk-level-{esc(level)}">{esc(level)}</strong>
            <small>{len(risks)} 个风险点</small>
          </div>
          <div class="risk-kpi">
            <span class="risk-kpi-label">严重度分布</span>
            <strong>{high_count}/{medium_count}/{low_count}</strong>
            <small>高 / 中 / 低</small>
          </div>
          <div class="risk-kpi">
            <span class="risk-kpi-label">待核验类别</span>
            <strong>{sum(1 for v in distribution.values() if v)}</strong>
            <small>{esc(_top_risk_type(distribution))}</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_risk_chips(distribution)


def _render_risk_chips(distribution: dict) -> None:
    chips = []
    for label in _TYPE_LABELS:
        count = distribution.get(label, 0)
        tone = "danger" if count and label in {"经历断层", "背调异常"} else "warning" if count else "neutral"
        chips.append(f'<span class="risk-chip {tone}"><b>{count}</b>{esc(label)}</span>')
    st.markdown(f'<div class="risk-chip-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def _render_risk_cards(risks: list[dict]) -> None:
    section("风险卡片", "HR 优先处理高风险项；证据保留给用人部门复核")
    if not risks:
        st.markdown(
            """
            <div class="risk-ok">
              <b>未发现明显风险</b>
              <span>建议按正常面试流程推进，面试中继续核实项目贡献和岗位动机。</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    sorted_risks = sorted(risks, key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.get("severity"), 3))
    for idx, risk in enumerate(sorted_risks, start=1):
        severity = risk.get("severity", "low")
        color = _SEVERITY_COLOR.get(severity, "#64748b")
        st.markdown(
            f"""
            <div class="risk-card">
              <div class="risk-card-head">
                <span class="risk-index" style="background:{color}">{idx}</span>
                <div>
                  <div class="risk-card-title">{esc(_business_risk_label(risk))}</div>
                  <div class="risk-card-sub">{esc(_SEVERITY_LABEL.get(severity, severity))}风险</div>
                </div>
                <span class="risk-card-badge" style="color:{color};background:{_tint_for(severity)}">{esc(_next_action_for(risk))}</span>
              </div>
              <div class="risk-card-detail">{esc(risk.get("detail", "需进一步核实"))}</div>
              <div class="risk-evidence"><span>证据</span>{esc(risk.get("evidence", "暂无明确证据"))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_verification_actions(focus: list[str], level: str) -> None:
    section("下一步核验清单")
    if not focus:
        focus = ["核实候选人在核心项目中的个人贡献", "确认入职动机、稳定性和薪资预期"]
    rows = []
    for idx, item in enumerate(focus[:6], start=1):
        owner = "HR" if idx <= 2 or "社保" in item or "证书" in item else "用人部门"
        method = "电话/材料核验" if owner == "HR" else "结构化面试追问"
        rows.append({"优先级": idx, "负责人": owner, "核验动作": item, "方式": method})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("推送给 HR", use_container_width=True):
            st.success("已生成 HR 核验待办（Demo）")
    with col_b:
        if st.button("推送给用人部门", use_container_width=True):
            st.success("已生成用人部门追问清单（Demo）")
    st.caption("Demo 版展示推送动作；真实接入时可写入北森/企业内部系统待办。")


def _render_background_check(candidate: dict, risks: list[dict], compact: bool = False) -> None:
    section("背调核验摘要", "把第三方背调报告折叠成 HR 可读的风险状态")
    checks = _background_items(candidate, risks)
    html = []
    for item in checks:
        tone = item["tone"]
        html.append(
            f"""
            <div class="risk-check-row {tone}">
              <span class="risk-check-dot"></span>
              <div><b>{esc(item["name"])}</b><small>{esc(item["result"])}</small></div>
              <em>{esc(item["status"])}</em>
            </div>
            """
        )
    cls = "risk-check-list compact" if compact else "risk-check-list"
    st.markdown(f'<div class="{cls}">{"".join(html)}</div>', unsafe_allow_html=True)


def _render_detail_table(risks: list[dict]) -> None:
    with st.expander("查看完整风险明细表"):
        if risks:
            rows = [{
                "风险类型": _business_risk_label(r),
                "严重度": _SEVERITY_LABEL.get(r.get("severity"), r.get("severity", "—")),
                "说明": r.get("detail", "—"),
                "证据": r.get("evidence", "—"),
                "建议动作": _next_action_for(r),
            } for r in risks]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.success("未发现明显风险点。")


def _render_raw(candidate: dict) -> None:
    with st.expander("查看候选人 JSON 字段"):
        st.json({
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "match_result": candidate.get("match_result"),
            "risk_report": candidate.get("risk_report"),
            "status": candidate.get("status"),
        })


def _render_risk_closure(candidate: dict, level: str, risks: list[dict], focus: list[str], decision: dict) -> None:
    section("风险闭环", "把风险转换为企业流程里的责任人、动作和推进条件")
    impact = _hiring_impact(level, risks)
    hr_tasks = _hr_tasks(candidate, risks, focus)
    dept_tasks = _department_tasks(candidate, risks, focus)
    st.markdown(
        f"""
        <div class="closure-grid">
          <div class="closure-summary">
            <span class="risk-eyebrow">是否影响录用</span>
            <strong class="closure-impact {impact["tone"]}">{esc(impact["label"])}</strong>
            <small>{esc(impact["reason"])}</small>
          </div>
          <div class="closure-summary">
            <span class="risk-eyebrow">流程状态</span>
            <strong>{esc(impact["status"])}</strong>
            <small>{esc(decision["sla"])}</small>
          </div>
          <div class="closure-summary">
            <span class="risk-eyebrow">主责人</span>
            <strong>{esc(decision["owner"])}</strong>
            <small>结果同步 HR 与用人部门</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_hr, tab_dept, tab_skill = st.tabs(["HR 核验清单", "用人部门追问", "技能真实性核验"])
    with tab_hr:
        st.dataframe(pd.DataFrame(hr_tasks), use_container_width=True, hide_index=True)
    with tab_dept:
        st.dataframe(pd.DataFrame(dept_tasks), use_container_width=True, hide_index=True)
    with tab_skill:
        st.dataframe(pd.DataFrame(_skill_verification_questions(candidate, risks)), use_container_width=True, hide_index=True)


def _hiring_impact(level: str, risks: list[dict]) -> dict:
    high_types = [str(r.get("type", "")) for r in risks if r.get("severity") == "high"]
    if level == "高" or high_types:
        return {
            "label": "影响录用",
            "tone": "danger",
            "status": "暂停推进，待核验",
            "reason": "存在硬风险或关键疑点，未完成核验前不建议进入 Offer。",
        }
    if level == "中":
        return {
            "label": "条件推进",
            "tone": "warning",
            "status": "可面试，需带问题核验",
            "reason": "风险可控但需要面试或材料补充确认。",
        }
    return {
        "label": "不影响",
        "tone": "success",
        "status": "正常推进",
        "reason": "当前未发现影响流程推进的关键风险。",
    }


def _hr_tasks(candidate: dict, risks: list[dict], focus: list[str]) -> list[dict]:
    tasks = []
    risk_text = " ".join(f"{r.get('type','')} {r.get('detail','')}" for r in risks)
    if "经历断层" in risk_text:
        tasks.append({"优先级": "P0", "核验事项": "工作经历断层", "动作": "要求候选人补充社保、劳动合同、离职证明或项目证明", "通过条件": "空档期解释可验证且与简历一致"})
    if "证书过期" in risk_text:
        tasks.append({"优先级": "P1", "核验事项": "证书/资质有效性", "动作": "要求提供证书编号、最新截图或官方查询结果", "通过条件": "证书状态有效或岗位不强依赖该证书"})
    if "频繁跳槽" in risk_text:
        tasks.append({"优先级": "P1", "核验事项": "稳定性", "动作": "电话初面逐段确认离职原因和职业预期", "通过条件": "离职原因合理，岗位预期稳定"})
    if "信息存疑" in risk_text or "技能存疑" in risk_text:
        tasks.append({"优先级": "P1", "核验事项": "简历包装/信息不一致", "动作": "要求候选人补充项目材料、汇报文档或证明人", "通过条件": "关键信息有材料或证明人支撑"})
    if not tasks:
        tasks.append({"优先级": "P2", "核验事项": "基础信息", "动作": "确认身份、学历、到岗时间、薪资预期", "通过条件": "基础信息一致"})
    return tasks[:5]


def _department_tasks(candidate: dict, risks: list[dict], focus: list[str]) -> list[dict]:
    tasks = []
    for idx, item in enumerate(focus[:4], start=1):
        tasks.append({
            "优先级": f"P{0 if idx == 1 else 1}",
            "追问方向": "风险核验" if idx <= 2 else "岗位短板",
            "面试问题": item if str(item).endswith("？") else f"{item}，请候选人现场说明。",
            "判断标准": "回答必须有具体场景、个人动作、数据结果或可验证证据",
        })
    match = candidate.get("match_result") or {}
    for gap in (match.get("gap_points") or [])[:2]:
        tasks.append({
            "优先级": "P1",
            "追问方向": "匹配差距",
            "面试问题": f"简历显示存在“{gap}”，请你说明是否有补充经历或学习计划。",
            "判断标准": "能正面回应短板，而不是回避或泛泛承诺",
        })
    if not tasks:
        tasks.append({"优先级": "P2", "追问方向": "胜任力", "面试问题": "请讲一个最能体现岗位胜任力的项目。", "判断标准": "能说明背景、任务、动作、结果"})
    return tasks[:6]


def _skill_verification_questions(candidate: dict, risks: list[dict]) -> list[dict]:
    skills = candidate.get("resume_parsed", {}).get("skills") or []
    suspicious = []
    risk_text = " ".join(f"{r.get('type','')} {r.get('detail','')} {r.get('evidence','')}" for r in risks)
    for skill in skills:
        if str(skill) in risk_text or len(suspicious) < 3:
            suspicious.append(str(skill))
    if not suspicious:
        suspicious = ["岗位核心技能"]
    rows = []
    for skill in suspicious[:4]:
        rows.append({
            "技能": skill,
            "核验问题": f"请说明你在真实项目中如何使用 {skill}，遇到过什么问题，最后怎么解决？",
            "合格信号": "能说出具体业务场景、技术/方法细节、个人贡献和结果数据",
            "风险信号": "只会说概念、无法说明个人动作、无法给出项目证据",
        })
    return rows


def _business_risk_label(risk: dict) -> str:
    rtype = str(risk.get("type", "风险点"))
    detail = str(risk.get("detail", ""))
    if rtype in {"信息存疑", "技能存疑"} or any(word in detail for word in ("自述", "缺少", "无法提供", "存疑")):
        return f"{rtype}（疑似包装）"
    return rtype


def _candidate_rows(candidates: list[dict]) -> list[dict]:
    rows = []
    for candidate in candidates:
        match = candidate.get("match_result") or {}
        report = candidate.get("risk_report") or {}
        risks = report.get("risks") or []
        level = report.get("level") or "未核验"
        score = _score(match.get("overall_score"))
        action = _batch_action(score, level, risks, match, candidate)
        tags = _batch_tags(candidate, risks)
        rows.append({
            "id": candidate.get("id"),
            "姓名": candidate.get("name", candidate.get("id", "—")),
            "匹配分": score,
            "风险等级": level,
            "推荐动作": action,
            "关键标签": " / ".join(tags[:3]) if tags else "暂无",
            "推荐理由": _batch_reason(score, level, risks, match),
            "_priority": _batch_priority(score, level, action),
        })
    return _sort_rows(rows, "综合推荐")


def _batch_background_stats(candidates: list[dict]) -> dict:
    clear = abnormal = pending = 0
    for candidate in candidates:
        items = _background_items(candidate, (candidate.get("risk_report") or {}).get("risks") or [])
        tones = [item.get("tone") for item in items]
        if "danger" in tones:
            abnormal += 1
        elif "warning" in tones:
            pending += 1
        else:
            clear += 1
    return {"ready": len(candidates), "clear": clear, "abnormal": abnormal, "pending": pending}


def _score(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _batch_action(score: int, level: str, risks: list[dict], match: dict, candidate: dict) -> str:
    risk_text = " ".join(map(str, [
        match.get("gap_points") or [],
        match.get("summary") or "",
        candidate.get("tags") or [],
    ]))
    if level == "未核验" and any(word in risk_text for word in ("经历断层", "证书过期", "高风险", "信息存疑", "技能存疑")):
        return "先核验"
    if level == "高" or any(r.get("severity") == "high" for r in risks):
        return "先核验"
    if score >= 85 and level in {"低", "未核验"}:
        return "优先推进"
    if score >= 70 and level in {"低", "中", "未核验"}:
        return "进入AI面试"
    if match.get("recommendation") == "不推进" or score < 55:
        return "暂不推进"
    return "备选观察"


def _batch_reason(score: int, level: str, risks: list[dict], match: dict) -> str:
    if level == "高" or any(r.get("severity") == "high" for r in risks):
        first = next((r for r in risks if r.get("severity") == "high"), risks[0] if risks else {})
        return f"高风险需先核验：{first.get('type', '关键风险')}"
    if score >= 85:
        return "匹配度高且风险可控，适合优先进入面试"
    if score >= 70:
        return "基本匹配，建议带着短板问题进入 AI 面试"
    if match.get("gap_points"):
        return f"匹配差距明显：{match.get('gap_points')[0]}"
    return "匹配度偏低，建议暂缓推进"


def _batch_tags(candidate: dict, risks: list[dict]) -> list[str]:
    tags = []
    for risk in risks:
        if risk.get("type"):
            tags.append(str(risk["type"]))
    tags.extend([str(t) for t in candidate.get("tags") or []])
    return list(dict.fromkeys(tags))


def _batch_priority(score: int, level: str, action: str) -> float:
    risk_penalty = {"高": 70, "中": 25, "低": 0, "未核验": 10}.get(level, 15)
    action_bonus = {"优先推进": 35, "进入AI面试": 20, "备选观察": 5, "先核验": -20, "暂不推进": -50}.get(action, 0)
    return score + action_bonus - risk_penalty


def _best_candidate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    viable = [r for r in rows if r["推荐动作"] in {"优先推进", "进入AI面试", "备选观察"}]
    pool = viable or rows
    return sorted(pool, key=lambda r: r["_priority"], reverse=True)[0]


def _filter_rows(rows: list[dict], risk_filter: str, action_filter: str) -> list[dict]:
    out = rows
    if risk_filter != "全部风险":
        out = [r for r in out if r["风险等级"] == risk_filter]
    if action_filter != "全部动作":
        out = [r for r in out if r["推荐动作"] == action_filter]
    return out


def _sort_rows(rows: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "匹配分最高":
        return sorted(rows, key=lambda r: r["匹配分"], reverse=True)
    if sort_by == "风险最高":
        rank = {"高": 3, "中": 2, "未核验": 1, "低": 0}
        return sorted(rows, key=lambda r: (rank.get(r["风险等级"], 0), r["匹配分"]), reverse=True)
    if sort_by == "待核验优先":
        return sorted(rows, key=lambda r: (r["推荐动作"] == "先核验", r["风险等级"] == "高", r["匹配分"]), reverse=True)
    return sorted(rows, key=lambda r: r["_priority"], reverse=True)


def _action_tone(action: str) -> str:
    if action == "优先推进":
        return "success"
    if action == "进入AI面试":
        return "brand"
    if action == "先核验":
        return "warning"
    if action == "暂不推进":
        return "danger"
    return "neutral"


def _risk_distribution(risks: list[dict]) -> dict:
    out = {label: 0 for label in _TYPE_LABELS}
    for risk in risks:
        rtype = str(risk.get("type", ""))
        matched = next((label for label in _TYPE_LABELS if label in rtype), None)
        if matched:
            out[matched] += 1
        elif "身份" in rtype or "学历" in rtype:
            out["背调异常"] += 1
    return out


def _top_risk_type(distribution: dict) -> str:
    active = [(k, v) for k, v in distribution.items() if v]
    if not active:
        return "暂无明显风险"
    active.sort(key=lambda item: item[1], reverse=True)
    return active[0][0]


def _decision_for(level: str, risks: list[dict], match: dict) -> dict:
    has_identity_or_gap = any(r.get("severity") == "high" for r in risks)
    score = match.get("overall_score", 0)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0
    if level == "高" or has_identity_or_gap:
        return {
            "title": "暂停推进，先完成关键核验",
            "copy": "存在会影响录用判断的硬风险。建议 HR 先核验证据，再决定是否进入下一轮。",
            "owner": "HR 主责",
            "sla": "今日内处理",
        }
    if level == "中":
        return {
            "title": "可进入面试，但必须带问题核验",
            "copy": "候选人仍可比较，但面试官需要围绕疑点追问，避免主观印象替代证据。",
            "owner": "HR + 用人部门",
            "sla": "面试前完成",
        }
    if score >= 80:
        return {
            "title": "风险可控，建议正常推进",
            "copy": "当前未发现影响推进的明显风险，面试重点放在岗位胜任力和团队适配。",
            "owner": "用人部门复核",
            "sla": "正常流程",
        }
    return {
        "title": "风险可控，但匹配度需复核",
        "copy": "风险不是主要问题，建议结合岗位匹配分和候选人短板决定是否继续。",
        "owner": "用人部门复核",
        "sla": "正常流程",
    }


def _next_action_for(risk: dict) -> str:
    rtype = str(risk.get("type", ""))
    severity = risk.get("severity")
    if "经历断层" in rtype:
        return "补充证明"
    if "证书过期" in rtype:
        return "查验证书"
    if "频繁跳槽" in rtype:
        return "追问稳定性"
    if "技能存疑" in rtype:
        return "技术追问"
    if "信息存疑" in rtype:
        return "材料核验"
    return "暂停" if severity == "high" else "复核"


def _background_items(candidate: dict, risks: list[dict]) -> list[dict]:
    background = candidate.get("background_check") or {}
    if background.get("items"):
        return background["items"]
    text = " ".join(f"{r.get('type','')} {r.get('detail','')}" for r in risks)
    has_cert = "证书过期" in text
    has_gap = "经历断层" in text
    has_identity = "身份" in text or "姓名" in text
    has_lawsuit = "诉讼" in text or "被执行" in text
    has_credit = "网贷" in text or "逾期" in text
    has_business = "商业关联" in text or "法人" in text or "高管" in text
    return [
        {"name": "身份信息", "status": "异常" if has_identity else "通过", "result": "姓名与证件一致性" + ("待复核" if has_identity else "未发现异常"), "tone": "danger" if has_identity else "success"},
        {"name": "社会安全/犯罪风险", "status": "通过", "result": "未发现犯罪或社会安全异常记录", "tone": "success"},
        {"name": "吸毒记录", "status": "通过", "result": "未发现异常记录", "tone": "success"},
        {"name": "网贷信用", "status": "异常" if has_credit else "通过", "result": "存在逾期/信用疑点" if has_credit else "当前未发现逾期风险", "tone": "danger" if has_credit else "success"},
        {"name": "诉讼/被执行人", "status": "异常" if has_lawsuit else "通过", "result": "存在诉讼或被执行疑点" if has_lawsuit else "未发现诉讼及被执行记录", "tone": "danger" if has_lawsuit else "success"},
        {"name": "商业关联风险", "status": "异常" if has_business else "通过", "result": "存在企业任职/股权疑点" if has_business else "未发现高风险商业关联", "tone": "danger" if has_business else "success"},
        {"name": "学历核验", "status": "待核验" if has_cert else "通过", "result": "学历/证书材料建议复查" if has_cert else "学历信息暂未发现异常", "tone": "warning" if has_cert else "success"},
        {"name": "学位核验", "status": "待核验" if has_cert else "通过", "result": "学位或证书编号待复查" if has_cert else "学位信息暂未发现异常", "tone": "warning" if has_cert else "success"},
        {"name": "工作履历", "status": "异常" if has_gap else "通过", "result": "存在未解释空档期" if has_gap else "履历连续性正常", "tone": "danger" if has_gap else "success"},
    ]


def _tint_for(severity: str) -> str:
    return {"high": "#fef2f2", "medium": "#fffbeb", "low": "#ecfdf5"}.get(severity, "#f8fafc")


def _inject_risk_styles() -> None:
    st.markdown(
        """
        <style>
        .risk-command {
            display:flex; align-items:center; justify-content:space-between; gap:18px;
            padding:16px 18px; background:#fff; border:1px solid var(--border);
            border-radius:14px; margin:6px 0 12px;
        }
        .batch-hero {
            display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:18px; align-items:stretch;
            padding:18px; background:#fff; border:1px solid var(--border); border-radius:14px; margin:6px 0 14px;
        }
        .batch-title { color:var(--text); font-size:24px; font-weight:760; line-height:1.22; }
        .batch-sub { color:var(--text-2); font-size:13px; margin-top:7px; }
        .batch-best {
            display:flex; flex-direction:column; justify-content:center;
            background:var(--brand-50); border:1px solid var(--brand-100); border-radius:12px; padding:14px;
        }
        .batch-best span { color:var(--brand); font-size:12px; font-weight:650; }
        .batch-best strong { color:var(--text); font-size:22px; line-height:1.15; margin-top:4px; }
        .batch-best small { color:var(--text-2); font-size:12px; line-height:1.45; margin-top:7px; }
        .batch-bg-strip {
            display:flex; align-items:center; justify-content:space-between; gap:14px;
            background:#fff; border:1px solid var(--border); border-radius:12px; padding:13px 15px; margin:0 0 12px;
        }
        .batch-bg-strip strong { display:block; color:var(--text); font-size:16px; line-height:1.25; margin-top:2px; }
        .batch-bg-strip small { display:block; color:var(--text-2); font-size:12px; margin-top:4px; }
        .batch-bg-states { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:6px; }
        .candidate-list-head { color:var(--text); font-size:15px; font-weight:700; margin:16px 0 8px; }
        .candidate-row {
            background:#fff; border:1px solid var(--border); border-radius:12px;
            padding:13px 15px; margin-top:8px;
        }
        .candidate-name { color:var(--text); font-size:16px; font-weight:730; line-height:1.2; }
        .candidate-reason { color:var(--text-2); font-size:13px; line-height:1.45; margin-top:5px; }
        .candidate-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:9px; }
        .risk-eyebrow { font-size:12px; color:var(--text-3); margin-bottom:4px; }
        .risk-name { font-size:22px; color:var(--text); font-weight:720; line-height:1.2; }
        .risk-meta { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:8px; font-size:13px; color:var(--text-2); }
        .risk-tags { display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; max-width:48%; }

        .risk-decision {
            display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:24px; align-items:center;
            background:#fff; border:1px solid color-mix(in srgb, var(--risk-color) 28%, var(--border));
            border-radius:14px; padding:20px; margin:6px 0 14px;
        }
        .risk-decision-title { font-size:24px; font-weight:760; color:var(--text); line-height:1.25; }
        .risk-decision-copy { margin-top:8px; color:var(--text-2); font-size:14px; line-height:1.65; max-width:70ch; }
        .risk-action-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
        .risk-meter { padding:16px; background:var(--surface-2); border:1px solid var(--border); border-radius:12px; }
        .risk-meter-label { color:var(--text-3); font-size:12px; }
        .risk-meter-value { font-size:36px; font-weight:780; line-height:1.1; margin-top:3px; }
        .risk-meter-track { height:9px; background:#e2e8f0; border-radius:999px; overflow:hidden; margin-top:14px; }
        .risk-meter-fill { height:100%; width:var(--risk-progress); background:var(--risk-color); border-radius:999px; }
        .risk-meter-scale { display:flex; justify-content:space-between; color:var(--text-3); font-size:11px; margin-top:7px; }

        .risk-kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:14px 0; }
        .risk-kpi { background:#fff; border:1px solid var(--border); border-radius:12px; padding:14px 15px; }
        .risk-kpi-label { display:block; color:var(--text-3); font-size:12px; margin-bottom:7px; }
        .risk-kpi strong { display:block; font-size:24px; color:var(--text); line-height:1.05; }
        .risk-kpi small { display:block; color:var(--text-3); margin-top:7px; font-size:12px; }
        .risk-level-高 { color:var(--danger)!important; }
        .risk-level-中 { color:var(--warning)!important; }
        .risk-level-低 { color:var(--success)!important; }

        .risk-chip-row { display:flex; flex-wrap:wrap; gap:8px; margin:4px 0 16px; }
        .risk-chip {
            display:inline-flex; align-items:center; gap:6px; padding:7px 10px; border-radius:999px;
            border:1px solid var(--border); background:#fff; color:var(--text-2); font-size:12px;
        }
        .risk-chip b { font-size:13px; color:var(--text); }
        .risk-chip.warning { background:var(--warning-bg); border-color:#fde68a; color:#92400e; }
        .risk-chip.danger { background:var(--danger-bg); border-color:#fecaca; color:#991b1b; }

        .closure-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:14px 0 8px; }
        .closure-summary { background:#fff; border:1px solid var(--border); border-radius:12px; padding:14px 15px; }
        .closure-summary strong { display:block; color:var(--text); font-size:18px; line-height:1.2; margin-top:4px; }
        .closure-summary small { display:block; color:var(--text-2); line-height:1.5; margin-top:8px; }
        .closure-impact.danger { color:var(--danger)!important; }
        .closure-impact.warning { color:var(--warning)!important; }
        .closure-impact.success { color:var(--success)!important; }

        .risk-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:15px; margin-bottom:10px; }
        .risk-card-head { display:flex; align-items:center; gap:11px; }
        .risk-index { width:28px; height:28px; flex:0 0 28px; border-radius:8px; color:#fff; display:inline-flex; align-items:center; justify-content:center; font-weight:720; font-size:13px; }
        .risk-card-title { color:var(--text); font-size:15px; font-weight:700; }
        .risk-card-sub { color:var(--text-3); font-size:12px; margin-top:1px; }
        .risk-card-badge { margin-left:auto; padding:4px 9px; border-radius:999px; font-size:12px; font-style:normal; font-weight:650; }
        .risk-card-detail { color:var(--text-2); margin-top:12px; line-height:1.58; font-size:13px; }
        .risk-evidence { margin-top:10px; padding:10px 11px; background:var(--surface-2); border-radius:9px; color:var(--text-2); font-size:12px; line-height:1.55; }
        .risk-evidence span { color:var(--text-3); font-weight:650; margin-right:8px; }

        .risk-check-list { display:flex; flex-direction:column; gap:8px; }
        .risk-check-list.compact { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin:8px 0 14px; }
        .risk-check-row { display:grid; grid-template-columns:10px 1fr auto; gap:10px; align-items:center; padding:10px 11px; background:#fff; border:1px solid var(--border); border-radius:10px; }
        .risk-check-dot { width:8px; height:8px; border-radius:50%; background:var(--text-3); }
        .risk-check-row b { display:block; color:var(--text); font-size:13px; }
        .risk-check-row small { display:block; color:var(--text-3); margin-top:2px; line-height:1.35; }
        .risk-check-row em { font-style:normal; font-size:12px; color:var(--text-2); }
        .risk-check-row.success .risk-check-dot { background:var(--success); }
        .risk-check-row.warning .risk-check-dot { background:var(--warning); }
        .risk-check-row.danger .risk-check-dot { background:var(--danger); }

        .risk-empty, .risk-ok { display:flex; gap:14px; align-items:flex-start; padding:18px; background:#fff; border:1px dashed var(--border-2); border-radius:14px; }
        .risk-empty-icon { width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; background:var(--brand-50); color:var(--brand); font-weight:800; }
        .risk-empty-title, .risk-ok b { color:var(--text); font-size:15px; font-weight:720; }
        .risk-empty-text, .risk-ok span { display:block; color:var(--text-2); font-size:13px; line-height:1.6; margin-top:4px; }

        @media (max-width: 900px) {
          .risk-command, .risk-decision, .batch-hero { display:block; }
          .batch-best { margin-top:12px; }
          .batch-bg-strip { display:block; }
          .batch-bg-states { justify-content:flex-start; margin-top:10px; }
          .risk-tags { justify-content:flex-start; max-width:none; margin-top:12px; }
          .risk-meter { margin-top:16px; }
          .risk-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
          .closure-grid { grid-template-columns:1fr; }
          .risk-check-list.compact { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
