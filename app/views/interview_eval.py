"""面试辅助页面：候选人专属档案、固定9道题和评价表。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.evaluation import (
    build_candidate_interview_context,
    generate_interview_eval,
    generate_interview_questions,
)
from app.shared import list_candidates, load_candidate, load_jd, update_candidate
from app.ui import evidence_list, page_header, pill, score_bars, section, stat_grid


SAMPLE_NOTES = """面试官：请介绍你最相关的项目和个人贡献。
候选人：我负责定位核心问题，建立数据看板，并协调研发和生产共同推进改善。项目上线三个月后，问题发生率下降了28%。
面试官：遇到跨部门意见不一致时怎么处理？
候选人：我会先统一衡量指标，用小范围验证结果推动共识。之前先在一条产线试行，两周后数据改善，再推广到其他团队。
面试官：你认为自己目前最大的短板是什么？
候选人：复杂供应商协同经验还不够，我正在通过参与审核和复盘补足。"""


def render() -> None:
    _styles()
    page_header("面试辅助", "把岗位和候选人信息合成专属面试包，固定生成9道结构化问题", "✦")
    jd, candidates = load_jd(), list_candidates()
    if not jd or not candidates:
        st.warning("请先完成岗位设置、简历筛选和风险核验。")
        return

    selected_id = _selector(candidates)
    candidate = load_candidate(selected_id) or {}
    context = build_candidate_interview_context(candidate, jd)
    _context(candidate, context)
    _questions(candidate, jd)
    _notes_and_eval(candidate, jd)


def _selector(candidates: list[dict]) -> str:
    options = [candidate["id"] for candidate in candidates if candidate.get("id")]
    names = {candidate["id"]: candidate.get("name", candidate["id"]) for candidate in candidates}
    preferred = st.session_state.get("selected_candidate_id")
    index = options.index(preferred) if preferred in options else 0
    selected = st.selectbox("选择候选人", options, index=index, format_func=lambda cid: f"{names[cid]} · {cid}")
    st.session_state["selected_candidate_id"] = selected
    return selected


def _context(candidate: dict, context: dict) -> None:
    match, risk = context["screening"], context["risk"]
    section("候选人专属面试档案", "原始JD保持不变，本档案只为当前候选人的面试提供完整上下文")
    stat_grid([
        {"label": "候选人", "value": candidate.get("name", candidate.get("id"))},
        {"label": "目标岗位", "value": context["job"]["title"]},
        {"label": "匹配分", "value": match.get("overall_score", "—")},
        {"label": "风险等级", "value": risk.get("level", "未核验")},
    ])
    left, right = st.columns(2)
    with left:
        st.markdown("**匹配优势**")
        evidence_list(match.get("matched_points") or [], "success", "✓", "暂无")
        st.markdown("**主要短板**")
        evidence_list(match.get("gap_points") or [], "warning", "!", "暂无")
    with right:
        st.markdown("**风险与核验重点**")
        evidence_list(risk.get("interview_focus") or [], "warning", "!", "暂无明显风险")
        skills = context["candidate"]["resume"].get("skills") or []
        if skills:
            st.markdown(" ".join(pill(skill, "neutral") for skill in skills[:8]), unsafe_allow_html=True)
    with st.expander("查看原始JD与候选人结构化信息"):
        st.markdown(context["job"].get("raw_text") or "暂无JD原文")
        st.json(context["candidate"].get("resume") or {})


def _questions(candidate: dict, jd: dict) -> None:
    section("固定9道结构化面试题", "3道专业＋2道项目＋2道风险＋1道软实力＋1道综合判断")
    col_a, col_b = st.columns([1, 1])
    with col_a:
        use_llm = st.toggle("启用AI个性化出题", value=True, key="question_use_llm")
    with col_b:
        if st.button("生成候选人专属面试包", type="primary", use_container_width=True):
            with st.status("正在生成9道题...", expanded=True) as status:
                questions = generate_interview_questions(candidate, jd, use_llm=use_llm)
                st.session_state[f"questions_{candidate.get('id')}"] = questions
                status.update(label="专属面试包已生成", state="complete")

    questions = st.session_state.get(f"questions_{candidate.get('id')}") or []
    if not questions:
        st.info("点击按钮后，AI会结合JD、简历、匹配短板和风险报告生成严格9道题。")
        return
    rows = []
    for index, question in enumerate(questions, 1):
        rows.append({
            "序号": index,
            "维度": question.get("category", "—"),
            "问题": question.get("question", "—"),
            "考察目的": question.get("purpose", "—"),
            "好回答信号": question.get("good_answer_signal", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"当前共 {len(rows)} 道题；正式面试前可由面试官人工调整。")


def _notes_and_eval(candidate: dict, jd: dict) -> None:
    section("面试记录与评价", "支持粘贴线上转写或线下面试记录；记录形式本身不额外加分")
    notes = st.text_area(
        "面试记录",
        value=st.session_state.get(f"notes_{candidate.get('id')}", SAMPLE_NOTES),
        height=220,
        key=f"notes_{candidate.get('id')}",
    )
    left, right = st.columns([1, 1])
    with left:
        use_llm = st.toggle("启用AI生成评价", value=True, key="eval_use_llm")
    with right:
        if st.button("生成面试纪要与评价表", type="primary", use_container_width=True):
            with st.status("正在分析面试记录...", expanded=True) as status:
                status.write("结合岗位、简历、风险点和候选人回答")
                result = generate_interview_eval(candidate, notes, jd, use_llm=use_llm)
                update_candidate(candidate["id"], "interview_eval", result)
                update_candidate(candidate["id"], "status", "interviewed")
                status.update(label="评价表已生成，等待面试官复核", state="complete")
            st.rerun()

    result = (load_candidate(candidate.get("id")) or candidate).get("interview_eval")
    if not result:
        st.info("暂无面试评价。输入记录后生成，最终结果需要面试官确认。")
        return
    section("评价结论")
    form = result.get("form_filled") or {}
    stat_grid([
        {"label": "评级", "value": result.get("rating", "—")},
        {"label": "面试结论", "value": form.get("面试结论", "—")},
        {"label": "推荐动作", "value": form.get("推荐动作", "—")},
    ])
    section("维度评分")
    score_bars(list((result.get("dimension_scores") or {}).items()))
    section("AI面试纪要")
    st.write(result.get("summary", "—"))
    left, right = st.columns(2)
    with left:
        st.markdown("**关注点**")
        evidence_list(result.get("concerns") or [], "warning", "!", "暂无")
    with right:
        st.markdown("**回答证据**")
        evidence_list(result.get("evidence") or [], "success", "✓", "暂无引用证据")

    section("面试官复核")
    edited = st.data_editor(
        pd.DataFrame([{"字段": key, "内容": value} for key, value in form.items()]),
        use_container_width=True,
        hide_index=True,
        disabled=["字段"],
        key=f"eval_form_{candidate.get('id')}",
    )
    if st.button("确认提交评价", use_container_width=True):
        updated = dict(result)
        updated["form_filled"] = {str(row["字段"]): str(row["内容"]) for _, row in edited.iterrows()}
        updated["human_confirmed"] = True
        update_candidate(candidate["id"], "interview_eval", updated)
        st.success("评价已由面试官确认，可进入人才对比决策。")


def _styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff}
        </style>
        """,
        unsafe_allow_html=True,
    )
