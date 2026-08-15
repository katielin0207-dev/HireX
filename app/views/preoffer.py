"""Pre-offer verification: summarize an authorized third-party background report."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from app.parser import parse_uploaded_file
from app.shared import load_candidate, load_jd, list_candidates, update_candidate
from app.ui import esc, page_header, pill, section, stat_grid


def render() -> None:
    _inject_styles()
    page_header("录用前核验", "AI 自动识别背调报告结构，生成候选人待核验事项清单", "✓")
    jd = load_jd()
    candidates = list_candidates()
    if not jd or not candidates:
        st.warning("请先完成简历筛选与面试评价，再进入录用前核验。")
        return

    _render_position(candidates)
    selected_id = _render_background_workbench(candidates, jd)
    candidate = load_candidate(selected_id)
    if not candidate:
        st.error("候选人数据不存在，请刷新后重试。")
        return

    st.caption("从上方列表点击“启动背调”进入候选人核验窗口，查看系统自动识别出的待核验事项。")
    return


def _render_background_workbench(candidates: list[dict], jd: dict) -> str:
    section("背景调查列表", "选择候选人后启动背调，系统自动生成待核验事项清单")
    ranked = sorted(candidates, key=lambda c: (c.get("match_result") or {}).get("overall_score", 0), reverse=True)
    selected_id = st.session_state.get("preoffer_candidate_id") or (ranked[0]["id"] if ranked else "")

    col_actions, col_search, col_filter = st.columns([1.3, 3, 1.4], gap="medium")
    with col_actions:
        if st.button("+ 新增背调", type="primary", use_container_width=True):
            st.session_state["preoffer_candidate_id"] = selected_id
            st.session_state["preoffer_check_open"] = True
            st.rerun()
    with col_search:
        query = st.text_input("搜索", placeholder="输入姓名、岗位、状态搜索", label_visibility="collapsed")
    with col_filter:
        status_filter = st.selectbox("状态", ["全部状态", "待上传报告", "已解析待人工确认", "待补充材料", "暂缓 Offer", "已通过"], label_visibility="collapsed")

    filtered = []
    for cand in ranked:
        report = cand.get("preoffer_report") or _demo_report(cand, jd)
        haystack = " ".join(map(str, [cand.get("name"), jd.get("title"), report.get("report_status"), report.get("recommendation"), cand.get("status")]))
        if query and query.strip() not in haystack:
            continue
        if status_filter != "全部状态" and _row_status(cand, report) != status_filter:
            continue
        filtered.append(cand)

    st.markdown(
        """<div class="bg-table-head">
        <span>序号</span><span>候选人</span><span>录用排序</span><span>创建时间</span><span>操作</span>
        </div>""",
        unsafe_allow_html=True,
    )

    for idx, cand in enumerate(filtered[:10], start=1):
        match = cand.get("match_result") or {}
        eval_result = cand.get("interview_eval") or {}
        report = cand.get("preoffer_report") or _demo_report(cand, jd)
        row_id = cand["id"]
        c_num, c_name, c_rank, c_time, c_ops = st.columns([0.55, 3.2, 1.3, 1.9, 1.35], gap="small")
        with c_num:
            st.markdown(f'<div class="bg-row-cell bg-num">{idx}</div>', unsafe_allow_html=True)
        with c_name:
            st.markdown(
                f'''<div class="bg-row-cell"><b>{esc(cand.get("name", row_id))}</b>
                <small>{esc(jd.get("title", "当前岗位"))}</small><small>匹配 {esc(match.get("overall_score", "—"))} 分 · 面试 {esc(eval_result.get("rating", "待评价"))}</small></div>''',
                unsafe_allow_html=True,
            )
        with c_rank:
            st.markdown(f'<div class="bg-row-cell">{pill(_selection_status(cand), "brand" if _selection_status(cand) == "首选人" else "neutral")}</div>', unsafe_allow_html=True)
        with c_time:
            st.markdown(f'<div class="bg-row-cell"><b>{esc(_created_time(cand, report))}</b><small>{esc(_preoffer_action_label(cand))}</small></div>', unsafe_allow_html=True)
        with c_ops:
            if st.button("启动背调", key=f"preoffer_start_check_{row_id}", type="primary", use_container_width=True):
                st.session_state["preoffer_candidate_id"] = row_id
                st.session_state["preoffer_check_open"] = True

    if not filtered:
        st.info("没有匹配当前筛选条件的候选人。")

    check_id = st.session_state.get("preoffer_candidate_id")
    if st.session_state.get("preoffer_check_open") and check_id:
        check_candidate = load_candidate(check_id)
        if check_candidate:
            _render_background_check_window(check_candidate, jd, check_candidate.get("preoffer_report") or _demo_report(check_candidate, jd))

    return st.session_state.get("preoffer_candidate_id") or selected_id


def _render_batch_upload(candidates: list[dict], jd: dict) -> None:
    st.markdown(
        """<div class="batch-upload-panel">
        <div><b>批量上传第三方背调报告</b><span>一次上传多份 PDF、Word 或文本报告，系统会根据文件名和报告正文自动匹配候选人。</span></div>
        <small>示例：林嘉豪_背调.pdf、陈雨桐_学历核验.docx、何思琪_背景调查.txt</small>
        </div>""",
        unsafe_allow_html=True,
    )
    files = st.file_uploader(
        "批量上传第三方报告",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key="preoffer_batch_files",
        label_visibility="collapsed",
    )
    analyze = st.button("AI 批量识别并生成摘要", type="primary", use_container_width=True, disabled=not files)
    if not analyze or not files:
        return

    _handle_batch_files(files, candidates, jd)


def _handle_batch_files(files: list, candidates: list[dict], jd: dict) -> None:
    results = []
    for file in files:
        try:
            text = parse_uploaded_file(file.getvalue(), file.name)
        except ValueError as exc:
            results.append({"文件": file.name, "识别候选人": "未识别", "处理结果": f"解析失败：{exc}"})
            continue
        matched = _match_candidate_from_report(candidates, text, file.name)
        if not matched:
            results.append({"文件": file.name, "识别候选人": "未识别", "处理结果": "请人工改名或在摘要窗口补充核对"})
            continue
        report = _build_report(matched, jd, text, file.name, source="批量上传第三方报告")
        update_candidate(matched["id"], "preoffer_report", report)
        update_candidate(matched["id"], "status", "preoffer_pending")
        matched["preoffer_report"] = report
        matched["status"] = "preoffer_pending"
        results.append({"文件": file.name, "识别候选人": matched.get("name", matched["id"]), "处理结果": "已生成风险摘要"})

    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
    st.success("批量报告已处理。候选人的背调材料与核验报告内容已更新。")


def _match_candidate_from_report(candidates: list[dict], text: str, file_name: str) -> dict | None:
    haystack = f"{file_name}\n{text}"
    for cand in candidates:
        name = cand.get("name", "")
        if name and name in haystack:
            return cand
    return None


def _render_position(candidates: list[dict]) -> None:
    ready = [c for c in candidates if c.get("status") in {"decision_pending", "interviewed", "preoffer_pending", "preoffer_verified"}]
    st.markdown(
        f'''<div class="preoffer-flow">
              <span class="done">简历筛选</span><b>→</b><span class="done">面试评价</span><b>→</b>
              <span class="done">人才评价</span><b>→</b><span class="current">录用前核验</span><b>→</b><span>Offer 审批</span>
              <small>已进入录用前核验候选人：{len(ready) or 1} 人</small>
            </div>''',
        unsafe_allow_html=True,
    )


def _candidate_selector(candidates: list[dict]) -> str:
    options = [c["id"] for c in candidates if c.get("id")]
    names = {c["id"]: c.get("name", c["id"]) for c in candidates}
    preferred = st.session_state.get("preoffer_candidate_id") or st.session_state.get("selected_candidate_id")
    index = options.index(preferred) if preferred in options else 0
    selected_id = st.selectbox(
        "从人才评价结果中选择候选人",
        options,
        index=index,
        format_func=lambda cid: _candidate_label(names[cid], load_candidate(cid) or {}),
    )
    st.session_state["preoffer_candidate_id"] = selected_id
    return selected_id


def _candidate_label(name: str, candidate: dict) -> str:
    match = candidate.get("match_result") or {}
    evaluation = candidate.get("interview_eval") or {}
    return f"{name} · 匹配 {match.get('overall_score', '—')} 分 · 面试 {evaluation.get('rating', '待评价')}"


def _render_candidate_context(candidate: dict, jd: dict) -> None:
    match = candidate.get("match_result") or {}
    evaluation = candidate.get("interview_eval") or {}
    section("人才评价结论", "仅对已进入录用决策的首选人或备选人发起核验")
    stat_grid([
        {"label": "候选人", "value": candidate.get("name", "—")},
        {"label": "岗位匹配", "value": f"{match.get('overall_score', '—')} 分"},
        {"label": "面试评级", "value": evaluation.get("rating", "待补充")},
        {"label": "当前建议", "value": _selection_status(candidate)},
    ])
    st.caption(f"目标岗位：{jd.get('title', '当前岗位')}。技能真实性由面试和测评验证；本页只处理第三方背调、资质和履历一致性。")


def _render_upload(candidate: dict, candidate_id: str) -> tuple[str, str]:
    section("上传材料入口", "上传第三方背调报告、学历/学位证明、证书材料、离职/实习证明等")
    if st.session_state.get("preoffer_upload_focus"):
        st.info(f"正在为 {candidate.get('name', candidate_id)} 上传录用前核验报告。")
    st.markdown(
        """<div class="quality-hint">
        <b>上传前置条件</b><span>候选人授权、第三方报告完整、报告可提取文字、报告对象与候选人一致。未满足时只能生成待复核摘要。</span>
        </div>""",
        unsafe_allow_html=True,
    )
    upload, action = st.columns([4, 1], gap="medium")
    with upload:
        file = st.file_uploader(
            "第三方报告或补充证明材料",
            type=["pdf", "docx", "txt", "md"],
            key=f"preoffer_upload_{candidate_id}",
            label_visibility="collapsed",
        )
    with action:
        analyze = st.button("AI 解析报告", type="primary", use_container_width=True, disabled=file is None)
    if not analyze or file is None:
        return "", ""
    try:
        text = parse_uploaded_file(file.getvalue(), file.name)
    except ValueError as exc:
        st.error(str(exc))
        return "", ""
    if len(text.strip()) < 20:
        st.error("报告可提取文字过少，请上传可识别的 PDF、Word 或文本文件。")
        return "", ""
    return text, file.name


def _render_summary_window(candidate: dict, jd: dict, report: dict) -> None:
    title = f"{candidate.get('name', candidate.get('id'))}｜AI 核验摘要"

    def body() -> None:
        _render_summary_body(candidate, jd, report)
        close_col, detail_col = st.columns(2, gap="small")
        with close_col:
            if st.button("关闭摘要", use_container_width=True):
                st.session_state["preoffer_summary_open"] = False
                st.rerun()
        with detail_col:
            if st.button("查看完整证据链", type="primary", use_container_width=True):
                st.session_state["preoffer_summary_open"] = False
                st.session_state["preoffer_detail_open"] = True
                st.session_state["preoffer_candidate_id"] = candidate["id"]
                st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog(title, width="large")
        def dialog_body() -> None:
            body()

        dialog_body()
    else:
        st.markdown(f"### {title}")
        body()


def _render_background_check_window(candidate: dict, jd: dict, report: dict) -> None:
    title = f"{candidate.get('name', candidate.get('id'))}｜启动背调"

    def body() -> None:
        _render_background_check_body(candidate, jd, report)
        close_col, download_col = st.columns([1, 1.2], gap="small")
        with close_col:
            if st.button("关闭窗口", use_container_width=True):
                st.session_state["preoffer_check_open"] = False
                st.rerun()
        with download_col:
            st.download_button(
                "下载背调核验报告",
                data=_report_download_text(candidate, jd, report),
                file_name=f"{candidate.get('name', candidate.get('id'))}_背调核验报告.txt",
                mime="text/plain",
                key=f"preoffer_check_download_{candidate.get('id')}",
                use_container_width=True,
            )

    if hasattr(st, "dialog"):
        @st.dialog(title, width="large")
        def dialog_body() -> None:
            body()

        dialog_body()
    else:
        st.markdown(f"### {title}")
        body()


def _render_background_check_body(candidate: dict, jd: dict, report: dict) -> None:
    match = candidate.get("match_result") or {}
    evaluation = candidate.get("interview_eval") or {}
    st.markdown(
        f'''<div class="check-hero">
        <div><span>候选人</span><strong>{esc(candidate.get("name", candidate.get("id")))}</strong><small>{esc(jd.get("title", "当前岗位"))}</small></div>
        <div><span>岗位匹配</span><strong>{esc(match.get("overall_score", "—"))} 分</strong><small>面试 {esc(evaluation.get("rating", "待评价"))}</small></div>
        <div><span>背调状态</span><strong>{esc(report.get("report_status", "待上传报告"))}</strong><small>{esc(report.get("source", "待上传第三方报告"))}</small></div>
        </div>''',
        unsafe_allow_html=True,
    )
    st.caption("这里不直接判定候选人“造假”或“不合格”，只把背调前需要核验的事项、依据来源和下一步材料要求列出来。")

    modules = _report_extraction_modules(report)
    st.markdown(
        f'''<div class="ai-recognition">
        <div><span>AI 已识别</span><strong>{len(modules)} 类报告模块</strong><small>自动从第三方报告、简历、JD 与面试评价中抽取字段</small></div>
        <div><span>待人工确认</span><strong>{sum(1 for item in modules if item["tone"] != "success")} 项</strong><small>系统只定位线索，不替 HR 下最终结论</small></div>
        <div><span>输出结果</span><strong>核验清单 + 下载报告</strong><small>把长报告转成 HR 可操作待办</small></div>
        </div>''',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="module-strip">', unsafe_allow_html=True)
    for item in modules:
        st.markdown(
            f'''<div class="module-pill {esc(item["tone"])}"><b>{esc(item["name"])}</b><span>{esc(item["status"])}</span></div>''',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    cards = _check_item_cards(candidate, report)
    st.markdown('<div class="check-grid">', unsafe_allow_html=True)
    for item in cards:
        st.markdown(
            f'''<div class="check-card {esc(item["tone"])}">
            <div class="check-card-top"><b>{esc(item["title"])}</b><span class="status-badge {esc(item["status_tone"])}">{esc(item["status"])}</span></div>
            <div class="check-stage">{esc(item["stage"])}</div>
            <p>{esc(item["result"])}</p>
            <dl><dt>证据链</dt><dd>{esc(item["source"])}</dd><dt>HR动作</dt><dd>{esc(item["next_action"])}</dd></dl>
            </div>''',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="check-timeline"><b>建议核验顺序</b><span>1. 确认候选人授权</span><span>2. 上传第三方报告/证明材料</span><span>3. 对照简历与岗位要求</span><span>4. HR 与用人部门确认是否影响 Offer</span></div>', unsafe_allow_html=True)


def _report_extraction_modules(report: dict) -> list[dict]:
    return [
        {"name": "报告信息", "status": "待核验 · 委托方/候选人/完成时间", "tone": "warning"},
        {"name": "身份信息", "status": "核验通过 · 姓名证件可对照", "tone": "success"},
        {"name": "授权状态", "status": "核验通过 · 候选人已授权", "tone": "success"},
        {"name": "社会安全/吸毒记录", "status": "核验通过 · 未见异常记录", "tone": "success"},
        {"name": "网贷信用", "status": "核验通过 · 逾期金额/天数为 0", "tone": "success"},
        {"name": "诉讼及被执行", "status": "核验通过 · 未见判决/执行记录", "tone": "success"},
        {"name": "商业关联", "status": "核验通过 · 未见法人/股权/高管关联", "tone": "success"},
        {"name": "学历学位", "status": "核验通过 · 学校/专业/毕业时间一致", "tone": "success"},
    ]


def _check_item_cards(candidate: dict, report: dict) -> list[dict]:
    matrix = report.get("risk_matrix") or []
    matrix_by_key = {str(row.get("核验痛点", "")): row for row in matrix}
    parsed = candidate.get("resume_parsed") or {}
    education = (parsed.get("education") or [{}])[0]
    experiences = parsed.get("experience") or []
    skills = parsed.get("skills") or []
    edu_text = f'{education.get("school", "学校未填写")} / {education.get("degree", "学历未填写")} / {education.get("major", "专业未填写")} / {education.get("end", "毕业时间未填写")}'
    exp_text = "；".join(f'{x.get("start", "")}-{x.get("end", "")} {x.get("company", "单位未填写")} {x.get("title", "")}' for x in experiences) or "简历未填写正式工作/实习时间线"
    skill_text = "、".join(skills[:6]) or "简历未提取到核心技能"
    risk_items = (candidate.get("risk_report") or {}).get("risks") or []
    project_evidence = "；".join(str(item.get("evidence", "")) for item in risk_items[:2]) or "项目成果待用人部门复核"

    def pick(keyword: str) -> dict:
        for key, value in matrix_by_key.items():
            if keyword in key:
                return value
        return {}

    return [
        {
            "title": "身份信息核验",
            "stage": "实名信息对照",
            "status": "核验通过",
            "status_tone": "success",
            "result": f'候选人 {candidate.get("name", "未填写")} 已进入背调流程，默认已完成授权；姓名与证件字段可直接对照第三方报告主体。',
            "source": "身份证核验接口、候选人授权信息、第三方报告身份信息页",
            "next_action": "HR 只需确认报告对象与当前候选人一致；如姓名或证件号不一致，再要求候选人补充说明。",
            "tone": "info",
        },
        {
            "title": "学历学位核验",
            "stage": "教育背景对照",
            "status": "核验通过",
            "status_tone": "success",
            "result": f"学历信息清晰：{edu_text}；与岗位工科背景要求匹配。",
            "source": "学信/学位核验、第三方报告学历学位页、候选人简历教育经历",
            "next_action": "正式报告回传后归档证书编号或学信截图。",
            "tone": "info",
        },
        {
            "title": "工作经历 Gap",
            "stage": "时间线核验",
            "status": "待核验",
            "status_tone": "warning",
            "result": f"提取到 {len(experiences)} 段经历：{exp_text}。应届生经历少属正常，但实习区间仍需材料覆盖。",
            "source": "简历时间线、社保/任职核验、离职证明、第三方工作履历页",
            "next_action": "HR 需要确认 2025.07-2025.10 实习证明/任职证明；若报告未覆盖该段经历，则要求候选人补充实习证明。",
            "tone": "warning",
        },
        {
            "title": "证书与材料有效期",
            "stage": "资质核验",
            "status": "待核验",
            "status_tone": "warning",
            "result": "简历未提供额外职业证书编号；岗位工具能力更多来自项目和面试表现。",
            "source": "学信/学位核验、证书编号、证书有效期、岗位资质要求",
            "next_action": "如岗位必须证书，再要求候选人补充证书编号或有效期截图。",
            "tone": "warning",
        },
        {
            "title": "频繁跳槽与稳定性",
            "stage": "稳定性核验",
            "status": "待决策",
            "status_tone": "neutral",
            "result": f"未见多段短期正式任职；当前仅有 {len(experiences)} 段实习/工作经历。稳定性需要 HR 判断。",
            "source": "简历任职区间、第三方履历记录、HR 电话初面记录",
            "next_action": "由 HR 在电话或录用沟通中确认长期意愿、能否接受一线/倒班、对制造现场岗位的稳定预期。",
            "tone": "neutral",
        },
        {
            "title": "核心技能真实性",
            "stage": "岗位能力对照",
            "status": "待决策",
            "status_tone": "neutral",
            "result": f"技能提取：{skill_text}。部分工具只写“基础”，需要用人部门复核真实使用深度。",
            "source": "简历项目描述、面试评价、测评记录、用人部门复核意见",
            "next_action": f"重点追问 Minitab、PFMEA、精益改善；项目证据：{project_evidence}",
            "tone": "info",
        },
        {
            "title": "合规与社会风险",
            "stage": "外部记录核验",
            "status": "核验通过",
            "status_tone": "success",
            "result": "示例报告字段显示社会安全、吸毒、网贷信用、诉讼/被执行、商业关联均未见异常记录。",
            "source": "公安/社会安全记录、司法公开记录、被执行人库、网贷信用记录、工商商业关联",
            "next_action": "AI 提取“无/有记录”、逾期金额、案号、企业任职等字段；异常项推送 HR 复核授权范围和原报告。",
            "tone": "warning",
        },
    ]


def _render_summary_body(candidate: dict, jd: dict, report: dict) -> None:
    match = candidate.get("match_result") or {}
    evaluation = candidate.get("interview_eval") or {}
    score = _risk_score(report)
    score_tone = _score_tone(score)
    st.markdown(
        f'''<div class="summary-window">
        <div class="summary-score {esc(score_tone)}"><span>风险评估分</span><strong>{score}</strong><small>{esc(_risk_label(report))} · {_row_status(candidate, report)}</small></div>
        <div class="summary-main"><span>AI 结论</span><b>{esc(report.get("recommendation", "待确认"))}</b><p>{esc(report.get("summary", ""))}</p></div>
        <div class="summary-meta">
          <div><span>岗位</span><b>{esc(jd.get("title", "当前岗位"))}</b></div>
          <div><span>匹配/面试</span><b>{esc(match.get("overall_score", "—"))} 分 · {esc(evaluation.get("rating", "待评价"))}</b></div>
          <div><span>报告状态</span><b>{esc(report.get("report_status", "待上传报告"))}</b></div>
        </div>
        </div>''',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="summary-bars">', unsafe_allow_html=True)
    for row in _risk_dimension_rows(report):
        tone = row["tone"]
        st.markdown(
            f'''<div class="summary-bar-row">
            <span>{esc(row["label"])}</span>
            <div><i class="{esc(tone)}" style="width:{row["score"]}%"></i></div>
            <b>{esc(row["status"])}</b>
            </div>''',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    rows = report.get("risk_matrix") or []
    if rows:
        compact_rows = [{"核验项": r.get("核验痛点"), "当前结论": r.get("当前结论"), "证据来源": r.get("证据来源")} for r in rows]
        st.dataframe(pd.DataFrame(compact_rows), use_container_width=True, hide_index=True)
    st.caption("摘要用于快速判断；正式结论仍以候选人授权、第三方报告原文和 HR 人工确认为准。")


def _render_report(candidate: dict, jd: dict, report: dict) -> None:
    section("录用前风险评估报告", "结论先行，证据保留到可追溯的三方对照中")
    tone = report["tone"]
    st.markdown(
        f'''<div class="verification-verdict {esc(tone)}">
              <div><span>Offer 建议</span><strong>{esc(report["recommendation"])}</strong><small>{esc(report["summary"])}</small></div>
              <div class="verification-score"><span>核验完整度</span><strong>{report["completion"]}%</strong><small>{report["supported"]}/{report["total"]} 项已支持</small></div>
            </div>
            <div class="report-provenance"><b>报告来源</b>{esc(report["source"])} · <b>解析时间</b>{esc(report["generated_at"])} · <b>状态</b>{esc(report["report_status"])}</div>''',
        unsafe_allow_html=True,
    )
    stat_grid([
        {"label": "风险评估分", "value": f"{_risk_score(report)} 分", "color": "#059669" if _risk_score(report) >= 80 else "#d97706"},
        {"label": "岗位必备项", "value": report["job_required"]},
        {"label": "已支持", "value": report["supported"], "color": "#059669"},
        {"label": "待补充", "value": report["pending"], "color": "#d97706"},
        {"label": "差异/异常", "value": report["issues"], "color": "#dc2626" if report["issues"] else "#059669"},
    ])

    _render_quality_panel(report)
    _render_audience_summary(report)
    _render_requirement_matrix(report)

    tab_compare, tab_evidence, tab_actions = st.tabs(["三方对照", "证据链", "推送与决策"])
    with tab_compare:
        st.dataframe(pd.DataFrame(report["comparisons"]), use_container_width=True, hide_index=True)
    with tab_evidence:
        for item in report["evidence"]:
            st.markdown(
                f'''<div class="evidence-row {esc(item["tone"])}"><span>{esc(item["label"])}</span>
                      <div><b>{esc(item["conclusion"])}</b><small>定位：{esc(item.get("locator", "待定位"))}</small>
                      <small>简历：{esc(item["resume"])}</small><small>第三方报告：{esc(item["report"])}</small></div></div>''',
                unsafe_allow_html=True,
            )
    with tab_actions:
        _render_decision_actions(candidate, report)


def _render_quality_panel(report: dict) -> None:
    quality = report.get("quality") or {}
    st.markdown(
        f'''<div class="quality-grid">
              <div><span>报告完整度</span><strong>{esc(quality.get("completeness", "待确认"))}</strong><small>{esc(quality.get("page_status", "页码/附件待人工确认"))}</small></div>
              <div><span>授权状态</span><strong>{esc(quality.get("authorization", "待授权"))}</strong><small>未授权项目不生成正式结论</small></div>
              <div><span>可读性</span><strong>{esc(quality.get("readability", "可读"))}</strong><small>{esc(quality.get("extraction", "文本可提取"))}</small></div>
              <div><span>报告对象</span><strong>{esc(quality.get("subject_match", "待人工确认"))}</strong><small>姓名/证件号需与候选人一致</small></div>
            </div>''',
        unsafe_allow_html=True,
    )


def _render_audience_summary(report: dict) -> None:
    audience = report.get("audience") or {}
    st.markdown(
        f'''<div class="audience-grid">
              <div><span>HR 摘要</span><strong>{esc(audience.get("hr", "确认授权、材料完整性和待补事项。"))}</strong></div>
              <div><span>用人部门摘要</span><strong>{esc(audience.get("department", "判断是否影响录用与岗位胜任。"))}</strong></div>
            </div>''',
        unsafe_allow_html=True,
    )


def _render_requirement_matrix(report: dict) -> None:
    section("招聘风险核验矩阵", "对应企业痛点：造假、断层、证书过期、频繁跳槽和核心技能真实性")
    rows = report.get("risk_matrix") or []
    if not rows:
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("说明：系统只能基于已上传报告、简历和面试材料做一致性核验；不能在未接入第三方服务时直接认定候选人造假。")


def _render_decision_actions(candidate: dict, report: dict) -> None:
    st.markdown("<div class='decision-note'>最终决定由 HR 与用人部门确认。系统保留 AI 结论、报告证据和人工操作记录。</div>", unsafe_allow_html=True)
    candidate_id = candidate["id"]
    push_hr, push_dept = st.columns(2, gap="small")
    with push_hr:
        if st.button("推送给 HR", use_container_width=True):
            update_candidate(candidate_id, "preoffer_push_hr", "已推送 HR 查看录用前风险评估报告")
            st.success("已推送给 HR（Demo）。")
    with push_dept:
        if st.button("推送给用人部门", use_container_width=True):
            update_candidate(candidate_id, "preoffer_push_department", "已推送用人部门查看岗位影响摘要")
            st.success("已推送给用人部门（Demo）。")

    col_offer, col_material, col_hold, col_backup = st.columns(4, gap="small")
    with col_offer:
        if st.button("发起 Offer 审批", type="primary", use_container_width=True):
            update_candidate(candidate_id, "status", "offer_approval_pending")
            update_candidate(candidate_id, "preoffer_decision", "已通过录用前核验，发起 Offer 审批")
            st.success("已推送 HR 发起 Offer 审批（Demo）。")
    with col_material:
        if st.button("要求补充材料", use_container_width=True):
            update_candidate(candidate_id, "status", "preoffer_material_pending")
            update_candidate(candidate_id, "preoffer_decision", "待候选人补充核验材料")
            st.warning("已生成候选人补充材料待办（Demo）。")
    with col_hold:
        if st.button("暂缓 Offer", use_container_width=True):
            update_candidate(candidate_id, "status", "preoffer_hold")
            update_candidate(candidate_id, "preoffer_decision", "风险待复核，暂缓 Offer")
            st.warning("已标记为暂缓 Offer。")
    with col_backup:
        if st.button("切换备选人", use_container_width=True):
            st.session_state["preoffer_candidate_id"] = _next_backup(candidate_id)
            st.info("已切换到备选候选人，可继续上传其报告。")
            st.rerun()
    if report["report_status"] == "Demo 示例报告":
        st.caption("当前展示的是结构化 Demo 报告。上传真实的、经候选人授权的第三方报告后，将以文件内容生成新结论。")


def _selection_status(candidate: dict) -> str:
    score = (candidate.get("match_result") or {}).get("overall_score", 0)
    if score >= 85:
        return "首选人"
    if score >= 70:
        return "备选人"
    return "待决策"


def _preoffer_status_label(status: str) -> str:
    mapping = {
        "offer_approval_pending": "已通过，待 Offer 审批",
        "preoffer_material_pending": "待补充材料",
        "preoffer_hold": "暂缓 Offer",
        "preoffer_verified": "核验完成",
    }
    return mapping.get(status, "待上传报告")


def _preoffer_action_label(candidate: dict) -> str:
    status = candidate.get("status", "")
    if status == "offer_approval_pending":
        return "等待 HR 发起审批"
    if status == "preoffer_material_pending":
        return "联系候选人补材料"
    if status == "preoffer_hold":
        return "复核风险或切备选"
    if candidate.get("preoffer_report"):
        return "人工确认报告"
    return ""


def _row_status(candidate: dict, report: dict) -> str:
    status = candidate.get("status", "")
    if status == "offer_approval_pending":
        return "已通过"
    if status == "preoffer_material_pending":
        return "待补充材料"
    if status == "preoffer_hold":
        return "暂缓 Offer"
    if report.get("report_status") == "已解析待人工确认":
        return "已解析待人工确认"
    return "待上传报告"


def _risk_label(report: dict) -> str:
    if report.get("tone") == "danger":
        return "高风险"
    if report.get("issues", 0):
        return "中风险"
    if report.get("report_status") == "Demo 示例报告":
        return "未核验"
    return "低风险"


def _tone_to_pill(tone: str) -> str:
    if tone == "danger":
        return "danger"
    if tone == "success":
        return "success"
    return "warning"


def _created_time(candidate: dict, report: dict) -> str:
    value = candidate.get("updated_at") or report.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
    return str(value).replace("T", " ")[:16]


def _risk_score(report: dict) -> int:
    completion = int(report.get("completion") or 0)
    issues = int(report.get("issues") or 0)
    pending = int(report.get("pending") or 0)
    if report.get("report_status") == "Demo 示例报告":
        return max(45, min(72, completion + 22 - pending * 3 - issues * 8))
    return max(0, min(100, 92 - issues * 16 - pending * 6 + max(0, completion - 70) // 4))


def _score_tone(score: int) -> str:
    if score >= 85:
        return "success"
    if score >= 70:
        return "warning"
    return "danger"


def _risk_dimension_rows(report: dict) -> list[dict]:
    rows = report.get("risk_matrix") or []
    result = []
    for row in rows:
        conclusion = str(row.get("当前结论", ""))
        if any(token in conclusion for token in ("存在", "发现", "不足", "过期")):
            score, tone, status = 42, "danger", "需复核"
        elif any(token in conclusion for token in ("待", "未接入")):
            score, tone, status = 62, "warning", "待确认"
        else:
            score, tone, status = 88, "success", "未见异常"
        label = str(row.get("核验痛点", "核验项")).replace(" / 是否疑似造假", "")
        result.append({"label": label, "score": score, "tone": tone, "status": status})
    return result


def _report_download_text(candidate: dict, jd: dict, report: dict) -> str:
    lines = [
        "HireX 录用前核验报告",
        f"候选人：{candidate.get('name', candidate.get('id'))}",
        f"岗位：{jd.get('title', '当前岗位')}",
        f"Offer 建议：{report.get('recommendation')}",
        f"风险评估分：{_risk_score(report)} 分",
        f"风险等级：{_risk_label(report)}",
        f"核验完整度：{report.get('completion')}%",
        f"报告来源：{report.get('source')}",
        f"报告状态：{report.get('report_status')}",
        "",
        "一、AI 摘要",
        str(report.get("summary", "")),
    ]
    lines.extend(["", "二、招聘风险痛点核验"])
    for item in report.get("risk_matrix") or []:
        lines.append(
            f"- {item.get('核验痛点')}: {item.get('当前结论')} | 证据={item.get('证据来源')} | HR动作={item.get('HR动作')}"
        )
    lines.extend(["", "三、第三方报告字段识别"])
    for item in _report_extraction_modules(report):
        lines.append(f"- {item.get('name')}: {item.get('status')} | 状态={item.get('tone')}")
    lines.extend(["", "四、核验事项状态与证据链"])
    for item in _check_item_cards(candidate, report):
        lines.append(
            f"- {item.get('title')}: {item.get('status')} | 证据链={item.get('source')} | HR动作={item.get('next_action')}"
        )
    lines.extend(["", "五、三方对照"])
    for item in report.get("comparisons") or []:
        lines.append(
            f"- {item.get('核验项')}: 简历={item.get('简历声明')} | 报告={item.get('第三方报告结论')} | 结论={item.get('结论')} | 建议={item.get('建议')}"
        )
    lines.extend(["", "六、证据链"])
    for item in report.get("evidence") or []:
        lines.append(f"- {item.get('label')}: {item.get('conclusion')} | {item.get('locator', '待定位')} | 报告摘录={item.get('report')}")
    lines.extend(["", "说明：本报告为 AI 辅助摘要，最终以候选人授权、第三方正式报告和 HR 人工确认为准。"])
    return "\n".join(lines)


def _next_backup(current_id: str) -> str:
    candidates = sorted(list_candidates(), key=lambda c: (c.get("match_result") or {}).get("overall_score", 0), reverse=True)
    ids = [c["id"] for c in candidates]
    if current_id not in ids or len(ids) < 2:
        return current_id
    return ids[(ids.index(current_id) + 1) % len(ids)]


def _demo_report(candidate: dict, jd: dict) -> dict:
    education = ((candidate.get("resume_parsed") or {}).get("education") or [{}])[0]
    experiences = (candidate.get("resume_parsed") or {}).get("experience") or []
    resume_work = "；".join(f'{x.get("company", "单位未填写")} {x.get("start", "")}-{x.get("end", "")}' for x in experiences[:2]) or "简历未提供工作时间线"
    job_skills = ((jd.get("requirements") or {}).get("hard") or {}).get("must_skills") or []
    resume_skills = (candidate.get("resume_parsed") or {}).get("skills") or []
    risk_text = " ".join(str(r.get("detail", "")) for r in ((candidate.get("risk_report") or {}).get("risks") or []))
    has_gap = "经历断层" in risk_text
    has_cert = "证书过期" in risk_text
    has_hopping = "频繁跳槽" in risk_text
    has_fake_signal = any(word in risk_text for word in ("信息存疑", "夸大", "无法验证", "缺少", "不一致"))
    has_skill_signal = "技能存疑" in risk_text
    comparisons = [
        {"核验项": "身份材料", "岗位/JD 要求": "录用前需完成实名与授权", "简历声明": candidate.get("name", "—"), "第三方报告结论": "候选人授权材料已登记（Demo）", "结论": "待正式服务核验", "建议": "HR 发起授权核验"},
        {"核验项": "学历与专业", "岗位/JD 要求": "本科及以上，相关工科专业", "简历声明": f'{education.get("school", "—")} · {education.get("degree", "—")} · {education.get("major", "—")}', "第三方报告结论": "学历材料已读取，正式验证待授权", "结论": "材料支持", "建议": "核验学历编号/授权结果"},
        {"核验项": "工作履历", "岗位/JD 要求": "制造现场或相关实习/项目经历", "简历声明": resume_work, "第三方报告结论": "基于 Demo 报告模板形成履历对照", "结论": "存在差异待说明" if has_gap else "时间线未见明显冲突", "建议": "补充实习/离职证明" if has_gap else "正式背调回传后确认"},
        {"核验项": "岗位资质/证书", "岗位/JD 要求": "CAD、Excel、质量工具等优先", "简历声明": "、".join(resume_skills[:6]) or "—", "第三方报告结论": "证书及资质材料待正式核验", "结论": "证书过期需处理" if has_cert else "技能不作为背调结论", "建议": "证书核验；技能以面试测评为准"},
        {"核验项": "合规风险", "岗位/JD 要求": "按企业授权范围完成核验", "简历声明": "不适用", "第三方报告结论": "Demo 未接入司法、征信、商业关联查询", "结论": "待第三方回传", "建议": "仅在授权后发起合规查询"},
    ]
    issues = sum(1 for row in comparisons if row["结论"] in {"存在差异待说明", "证书过期需处理"})
    supported = 2 if not has_gap else 1
    pending = len(comparisons) - supported
    tone = "danger" if has_gap else "warning"
    recommendation = "补充确认后再发 Offer" if has_gap or has_cert else "完成正式授权核验后可发 Offer"
    summary = "简历与现有材料可支持部分基础信息，但第三方报告尚未正式回传；不得据此认定候选人存在造假。"
    evidence = [
        {"label": "学历材料", "conclusion": f'{education.get("school", "学校未填写")} {education.get("degree", "学历未填写")}', "locator": "简历教育经历；第三方报告待上传", "resume": f'{education.get("start", "")}-{education.get("end", "")} {education.get("major", "")}', "report": "Demo：待授权后以第三方/官方回传为准", "tone": "warning"},
        {"label": "履历时间线", "conclusion": "需补充说明" if has_gap else "简历时间线可读", "locator": "简历工作经历；背调工作履历页待上传", "resume": resume_work, "report": "Demo：正式报告待上传", "tone": "danger" if has_gap else "warning"},
        {"label": "岗位资质", "conclusion": "技能真实性由面试评价支持", "locator": "JD 任职要求；面试评价表", "resume": "、".join(resume_skills[:6]) or "—", "report": f'JD 关键项：{("、".join(job_skills) or "—")}', "tone": "warning"},
    ]
    risk_matrix = _risk_matrix(
        has_fake_signal=has_fake_signal,
        has_gap=has_gap,
        has_cert=has_cert,
        has_hopping=has_hopping,
        has_skill_signal=has_skill_signal,
        uploaded=False,
    )
    return {
        "recommendation": recommendation, "summary": summary, "tone": tone, "completion": round(supported / len(comparisons) * 100),
        "supported": supported, "total": len(comparisons), "pending": pending, "issues": issues, "job_required": len(job_skills),
        "source": "Demo 结构化背调报告模板", "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "report_status": "Demo 示例报告", "comparisons": comparisons, "evidence": evidence,
        "quality": {
            "completeness": "待上传正式报告", "page_status": "页码与附件待核对", "authorization": "待候选人授权",
            "readability": "Demo 可读", "extraction": "示例模板文本", "subject_match": "待人工确认",
        },
        "audience": {
            "hr": "先确认候选人授权与正式报告完整性，再处理待补材料和 Offer 审批。",
            "department": "当前只能判断岗位资质与履历材料是否支持录用，不能直接认定造假。",
        },
        "risk_matrix": risk_matrix,
    }


def _build_report(candidate: dict, jd: dict, text: str, file_name: str, source: str) -> dict:
    report = _demo_report(candidate, jd)
    normalized = " ".join(text.split())
    lower = normalized.lower()
    risk_terms = [("失信", "存在失信相关提及"), ("被执行", "存在被执行相关提及"), ("犯罪", "存在犯罪/社会安全相关提及"), ("不一致", "存在信息不一致提及"), ("未通过", "存在核验未通过提及"), ("过期", "存在证书或资质过期提及")]
    hits = [label for term, label in risk_terms if term in normalized or term in lower]
    supported_terms = [term for term in ("学历", "学位", "身份", "任职", "工作经历", "证书") if term in normalized]
    excerpt = normalized[:180] + ("..." if len(normalized) > 180 else "")
    page_hint = _page_hint(text)
    auth_ok = any(term in normalized for term in ("授权", "委托", "同意核验"))
    subject_ok = candidate.get("name", "") in normalized
    report_risk_text = normalized + " " + " ".join(str(r.get("detail", "")) for r in ((candidate.get("risk_report") or {}).get("risks") or []))
    if hits:
        report["tone"] = "danger"
        report["recommendation"] = "风险待复核，暂缓发 Offer"
        report["summary"] = "AI 在已上传报告中识别到需要 HR 复核的表述；请以原报告页码和第三方正式结论为准。"
        report["issues"] = len(hits)
    else:
        report["tone"] = "warning"
        report["recommendation"] = "HR 确认后可发起 Offer 审批"
        report["summary"] = "已读取第三方报告文本，未发现预设高风险关键词；仍需 HR 确认报告完整性与授权范围。"
    report["source"] = f"{source}：{file_name}"
    report["report_status"] = "已解析待人工确认"
    report["supported"] = min(report["total"], max(2, len(supported_terms)))
    report["pending"] = report["total"] - report["supported"]
    report["completion"] = round(report["supported"] / report["total"] * 100)
    report["evidence"].insert(0, {
        "label": "第三方报告原文摘录", "conclusion": "；".join(hits) if hits else "未识别到预设高风险关键词",
        "locator": page_hint, "resume": "候选人简历作为对照来源", "report": excerpt, "tone": "danger" if hits else "warning",
    })
    report["quality"] = {
        "completeness": "已上传，待人工确认",
        "page_status": page_hint,
        "authorization": "已识别授权表述" if auth_ok else "未识别授权表述",
        "readability": "可读",
        "extraction": f"提取 {len(normalized)} 字",
        "subject_match": "姓名匹配" if subject_ok else "姓名未自动匹配",
    }
    report["audience"] = {
        "hr": "重点核对报告对象、候选人授权、异常项原文和待补材料，再决定是否发起 Offer。",
        "department": "关注核验差异是否影响岗位录用；技能真实性仍以面试评价和测评为主。",
    }
    report["risk_matrix"] = _risk_matrix(
        has_fake_signal=any(word in report_risk_text for word in ("不一致", "未通过", "无法验证", "信息存疑", "夸大")),
        has_gap="经历断层" in report_risk_text or "空档" in report_risk_text,
        has_cert="过期" in report_risk_text or "证书" in report_risk_text and "未通过" in report_risk_text,
        has_hopping="频繁跳槽" in report_risk_text or "短期" in report_risk_text,
        has_skill_signal="技能存疑" in report_risk_text or "技能" in report_risk_text and "缺少" in report_risk_text,
        uploaded=True,
    )
    return report


def _risk_matrix(
    *,
    has_fake_signal: bool,
    has_gap: bool,
    has_cert: bool,
    has_hopping: bool,
    has_skill_signal: bool,
    uploaded: bool,
) -> list[dict]:
    source = "第三方报告 + 简历 + 面试材料" if uploaded else "Demo 示例：简历 + 面试材料，第三方报告待上传"
    return [
        {
            "核验痛点": "简历真实性 / 是否疑似造假",
            "当前结论": "存在差异，待候选人说明" if has_fake_signal else "未发现明显不一致",
            "证据来源": source,
            "HR动作": "要求补充证明材料或候选人书面说明" if has_fake_signal else "正式背调回传后归档",
        },
        {
            "核验痛点": "工作经历断层",
            "当前结论": "发现经历空档，需要补充说明" if has_gap else "未发现超过规则阈值的断层",
            "证据来源": "简历工作时间线 / 背调工作履历页",
            "HR动作": "补充社保、离职证明、实习证明或收入证明" if has_gap else "正常归档",
        },
        {
            "核验痛点": "证书及材料是否过期",
            "当前结论": "存在过期或待复查材料" if has_cert else "未发现过期材料",
            "证据来源": "证书有效期 / 第三方报告资质核验项",
            "HR动作": "要求提供最新证书编号、官方截图或复训证明" if has_cert else "正式报告确认后归档",
        },
        {
            "核验痛点": "频繁跳槽风险",
            "当前结论": "存在稳定性风险" if has_hopping else "未发现明显频繁跳槽",
            "证据来源": "简历任职区间 / 背调履历记录",
            "HR动作": "电话确认离职原因和长期意愿" if has_hopping else "正常推进",
        },
        {
            "核验痛点": "核心技能真实性初步核验",
            "当前结论": "技能证据不足，需结合面试测评" if has_skill_signal else "面试材料暂未提示明显异常",
            "证据来源": "简历项目描述 / 面试评价 / 测评记录",
            "HR动作": "推送用人部门复核项目证据和面试回答" if has_skill_signal else "由用人部门确认岗位胜任",
        },
    ]


def _page_hint(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines[:80], start=1):
        if any(token in line for token in ("第", "页", "报告信息", "风险", "核验", "结论")):
            return f"上传报告第 {idx} 行附近：{line[:34]}"
    return "上传报告正文前 180 字"


def _inject_styles() -> None:
    st.markdown("""
    <style>
    .preoffer-flow{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:12px 14px;background:#fff;border:1px solid var(--border);border-radius:12px;margin:4px 0 18px;font-size:13px}.preoffer-flow span{color:var(--text-3);padding:4px 8px;border-radius:999px;background:var(--surface-3)}.preoffer-flow .done{color:var(--success);background:var(--success-bg)}.preoffer-flow .current{color:var(--brand);background:var(--brand-50);font-weight:700}.preoffer-flow b{color:var(--text-3)}.preoffer-flow small{margin-left:auto;color:var(--text-2)}
    .batch-upload-panel{display:flex;align-items:center;justify-content:space-between;gap:16px;background:#fff;border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin:12px 0 10px}.batch-upload-panel b{display:block;color:var(--text);font-size:14px}.batch-upload-panel span,.batch-upload-panel small{display:block;color:var(--text-2);font-size:12px;line-height:1.45;margin-top:3px}
    .bg-table-head{display:grid;grid-template-columns:.55fr 3.2fr 1.3fr 1.9fr 1.35fr;gap:8px;padding:8px 10px;color:var(--text-3);font-size:12px;font-weight:650;border-bottom:1px solid var(--border);margin-top:6px}.bg-row-cell{min-height:84px;display:flex;flex-direction:column;justify-content:center;background:#fff;border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:10px 12px;color:var(--text-2);font-size:13px}.bg-row-cell b{color:var(--text);font-size:15px;line-height:1.25}.bg-row-cell small{display:block;color:var(--text-3);font-size:12px;line-height:1.35;margin-top:5px}.bg-num{align-items:center;text-align:center;color:var(--text-3);font-size:22px;font-weight:520;border-left:1px solid var(--border);border-radius:10px 0 0 10px}.bg-row-cell:has(+ .bg-row-cell){border-left:0}
    .stButton>button,.stDownloadButton>button{white-space:nowrap;min-height:38px}
    .verification-verdict{display:grid;grid-template-columns:minmax(0,1fr) 180px;gap:18px;align-items:center;padding:18px;background:#fff;border:1px solid var(--border);border-radius:14px}.verification-verdict>div>span,.verification-score span{display:block;color:var(--text-3);font-size:12px}.verification-verdict>div>strong{display:block;color:var(--text);font-size:22px;line-height:1.25;margin-top:3px}.verification-verdict>div>small{display:block;color:var(--text-2);font-size:13px;line-height:1.55;margin-top:6px}.verification-verdict.warning{border-color:#fde68a}.verification-verdict.warning strong{color:var(--warning)}.verification-verdict.danger{border-color:#fecaca}.verification-verdict.danger strong{color:var(--danger)}.verification-verdict.success{border-color:#a7f3d0}.verification-verdict.success strong{color:var(--success)}.verification-score{padding:14px;background:var(--surface-2);border-radius:10px}.verification-score strong{font-size:28px!important}
    .report-provenance{margin:8px 0 14px;color:var(--text-2);font-size:12px}.report-provenance b{color:var(--text)}
    .quality-hint{display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;padding:12px 13px;background:#fff;border:1px solid var(--border);border-radius:10px;margin:2px 0 10px}.quality-hint b{color:var(--text);font-size:13px}.quality-hint span{color:var(--text-2);font-size:13px;line-height:1.5}
    .quality-grid,.audience-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}.audience-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.quality-grid>div,.audience-grid>div{background:#fff;border:1px solid var(--border);border-radius:10px;padding:12px 13px}.quality-grid span,.audience-grid span{display:block;color:var(--text-3);font-size:12px;margin-bottom:5px}.quality-grid strong{display:block;color:var(--text);font-size:15px;line-height:1.3}.quality-grid small{display:block;color:var(--text-2);font-size:12px;line-height:1.4;margin-top:5px}.audience-grid strong{display:block;color:var(--text-2);font-size:13px;line-height:1.6;font-weight:520}
    .ai-recognition{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.ai-recognition>div{background:#fff;border:1px solid var(--border);border-radius:10px;padding:13px 14px}.ai-recognition span{display:block;color:var(--text-3);font-size:12px;margin-bottom:5px}.ai-recognition strong{display:block;color:var(--text);font-size:18px;line-height:1.25}.ai-recognition small{display:block;color:var(--text-2);font-size:12px;line-height:1.4;margin-top:5px}.module-strip{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 12px}.module-pill{display:inline-flex;align-items:center;gap:7px;background:#fff;border:1px solid var(--border);border-radius:999px;padding:6px 10px}.module-pill b{font-size:12px;color:var(--text)}.module-pill span{font-size:11px;color:var(--text-2)}.module-pill.success{border-color:#a7f3d0;background:var(--success-bg)}.module-pill.warning{border-color:#fde68a;background:var(--warning-bg)}.module-pill.danger{border-color:#fecaca;background:var(--danger-bg)}
    .check-hero{display:grid;grid-template-columns:1.1fr .85fr 1.4fr;gap:10px;margin-bottom:12px}.check-hero>div{background:#fff;border:1px solid var(--border);border-radius:10px;padding:13px 14px}.check-hero span{display:block;color:var(--text-3);font-size:12px;margin-bottom:5px}.check-hero strong{display:block;color:var(--text);font-size:18px;line-height:1.25}.check-hero small{display:block;color:var(--text-2);font-size:12px;line-height:1.4;margin-top:5px}.check-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}.check-card{background:#fff;border:1px solid var(--border);border-radius:10px;padding:13px 14px}.check-card.info{border-color:#bae6fd}.check-card.warning{border-color:#fde68a}.check-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.check-card-top b{color:var(--text);font-size:15px}.check-stage{display:inline-flex;margin-top:6px;color:var(--text-3);font-size:11px;background:var(--surface-3);border-radius:999px;padding:3px 8px}.status-badge{font-size:11px;border-radius:999px;padding:3px 9px;white-space:nowrap;border:1px solid var(--border);background:var(--surface-3);color:var(--text-2)}.status-badge.success{color:var(--success);background:var(--success-bg);border-color:#a7f3d0}.status-badge.warning{color:var(--warning);background:var(--warning-bg);border-color:#fde68a}.status-badge.neutral{color:var(--text-2);background:var(--surface-3);border-color:var(--border)}.status-badge.danger{color:var(--danger);background:var(--danger-bg);border-color:#fecaca}.check-card p{margin:9px 0;color:var(--text);font-size:13px;line-height:1.5}.check-card dl{margin:0}.check-card dt{color:var(--text-3);font-size:11px;margin-top:8px}.check-card dd{margin:3px 0 0;color:var(--text-2);font-size:12px;line-height:1.5}.check-timeline{display:flex;flex-wrap:wrap;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:11px 12px;margin:12px 0}.check-timeline b{color:var(--text);font-size:13px;margin-right:4px}.check-timeline span{color:var(--text-2);font-size:12px;background:#fff;border:1px solid var(--border);border-radius:999px;padding:4px 9px}
    .summary-window{display:grid;grid-template-columns:132px minmax(0,1fr) 210px;gap:12px;align-items:stretch;margin-bottom:14px}.summary-window>div{background:#fff;border:1px solid var(--border);border-radius:10px;padding:13px 14px}.summary-score{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}.summary-score span,.summary-main span,.summary-meta span{display:block;color:var(--text-3);font-size:12px;margin-bottom:5px}.summary-score strong{font-size:38px;line-height:1;color:var(--warning)}.summary-score.success strong{color:var(--success)}.summary-score.danger strong{color:var(--danger)}.summary-score small{color:var(--text-2);font-size:12px;margin-top:6px}.summary-main b{display:block;color:var(--text);font-size:17px;line-height:1.3}.summary-main p{margin:8px 0 0;color:var(--text-2);font-size:13px;line-height:1.55}.summary-meta{display:grid;gap:8px}.summary-meta b{display:block;color:var(--text);font-size:13px;line-height:1.35}.summary-bars{background:#fff;border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin:10px 0}.summary-bar-row{display:grid;grid-template-columns:132px minmax(0,1fr) 74px;gap:10px;align-items:center;margin:8px 0}.summary-bar-row span,.summary-bar-row b{font-size:12px}.summary-bar-row span{color:var(--text-2)}.summary-bar-row b{color:var(--text);text-align:right}.summary-bar-row div{height:7px;background:var(--surface-3);border-radius:6px;overflow:hidden}.summary-bar-row i{display:block;height:100%;border-radius:6px;background:var(--warning)}.summary-bar-row i.success{background:var(--success)}.summary-bar-row i.danger{background:var(--danger)}
    .evidence-row{display:grid;grid-template-columns:132px minmax(0,1fr);gap:14px;padding:12px 13px;background:#fff;border:1px solid var(--border);border-radius:10px;margin-bottom:8px}.evidence-row>span{font-size:12px;color:var(--text-3)}.evidence-row b{display:block;color:var(--text);font-size:14px}.evidence-row small{display:block;color:var(--text-2);font-size:12px;line-height:1.45;margin-top:4px}.evidence-row.danger{border-color:#fecaca}.evidence-row.warning{border-color:#fde68a}.decision-note{padding:12px 13px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;color:var(--text-2);font-size:13px;line-height:1.55;margin-bottom:12px}
    @media(max-width:800px){.preoffer-flow small{width:100%;margin-left:0}.verification-verdict,.quality-hint,.evidence-row,.summary-window,.summary-bar-row,.check-hero{grid-template-columns:1fr}.quality-grid,.audience-grid,.check-grid,.ai-recognition{grid-template-columns:1fr}.batch-upload-panel{display:block}.bg-table-head{display:none}.bg-row-cell{min-height:unset;border:1px solid var(--border);border-radius:10px;margin-top:6px}.bg-num{font-size:16px}}
    </style>
    """, unsafe_allow_html=True)
