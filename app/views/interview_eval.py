"""B module page: interview notes to structured evaluation form."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.evaluation import generate_interview_eval, generate_interview_questions
from app.shared import list_candidates, load_candidate, load_jd, update_candidate
from app.ui import evidence_list, page_header, score_bars, section, stat_grid


SAMPLE_NOTES = """面试官：请介绍你在核心项目里的职责。
候选人：我主要负责订单服务接口重构，把慢查询从 800ms 优化到 180ms，也参与了 Redis 缓存策略设计。
面试官：遇到线上问题怎么处理？
候选人：之前出现过库存扣减延迟，我先看监控定位到队列堆积，再临时扩容消费者，事后补了限流和告警。
面试官：你对 FastAPI 的使用深度？
候选人：用过依赖注入、中间件和异步接口，但复杂微服务治理经验还不多。"""


def render() -> None:
    page_header("面试辅助与评价表", "粘贴面试记录，自动整理纪要、维度打分和招聘系统评价表", "📝")

    jd = load_jd()
    candidates = list_candidates()
    if not jd or not candidates:
        st.warning("请先生成 Mock 数据，或让前序模块写入候选人。")
        return

    selected_id = _candidate_selector(candidates)
    candidate = load_candidate(selected_id)
    if not candidate:
        st.error("候选人数据不存在，请刷新后重试。")
        return

    _render_context(candidate)
    _render_questions(candidate, jd)

    section("面试记录")
    notes = st.text_area(
        "粘贴线上面试转写、线下面试纪要或手工记录",
        value=st.session_state.get("interview_notes", SAMPLE_NOTES),
        height=220,
        key="interview_notes",
    )

    col_a, col_b = st.columns([1, 1], gap="large")
    with col_a:
        use_llm = st.toggle("启用 AI 生成评价表", value=True)
    with col_b:
        if st.button("生成面试评价", type="primary", use_container_width=True):
            with st.status("正在生成评价表...", expanded=True) as status:
                st.write("读取匹配结果与风险报告")
                result = generate_interview_eval(candidate, notes, jd=jd, use_llm=use_llm)
                st.write("写入 interview_eval 字段")
                update_candidate(selected_id, "interview_eval", result)
                update_candidate(selected_id, "status", "interviewed")
                status.update(label="评价表已生成", state="complete")
            st.success("已写入 interview_eval")
            st.rerun()

    st.divider()
    candidate = load_candidate(selected_id) or candidate
    _render_eval(candidate.get("interview_eval"))


def _candidate_selector(candidates: list[dict]) -> str:
    options = [c["id"] for c in candidates if c.get("id")]
    names = {c["id"]: c.get("name", c["id"]) for c in candidates}
    preferred = st.session_state.get("selected_candidate_id")
    index = options.index(preferred) if preferred in options else 0
    return st.selectbox("选择候选人", options=options, index=index, format_func=lambda cid: f"{names[cid]} · {cid}")


def _render_context(candidate: dict) -> None:
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    section("候选人上下文")
    stat_grid([
        {"label": "候选人", "value": candidate.get("name", candidate.get("id"))},
        {"label": "匹配分", "value": match.get("overall_score", "—")},
        {"label": "风险等级", "value": risk.get("level", "未核验")},
        {"label": "推荐结论", "value": match.get("recommendation", "—")},
    ])
    if risk.get("interview_focus"):
        with st.expander("查看风险核验重点", expanded=False):
            evidence_list(risk.get("interview_focus"), "warning", "!", "暂无")


def _render_questions(candidate: dict, jd: dict) -> None:
    section("面试前题库", "根据岗位核心考察点、简历短板和风险报告生成个性化问题")
    col_a, col_b = st.columns([1, 1], gap="large")
    with col_a:
        use_llm = st.toggle("启用 AI 生成题库", value=True, key="question_use_llm")
    with col_b:
        if st.button("生成结构化面试题", use_container_width=True):
            questions = generate_interview_questions(candidate, jd=jd, use_llm=use_llm)
            st.session_state[f"questions_{candidate.get('id')}"] = questions
    questions = st.session_state.get(f"questions_{candidate.get('id')}") or []
    if questions:
        rows = [{
            "维度": q.get("category", "—"),
            "问题": q.get("question", "—"),
            "考察目的": q.get("purpose", "—"),
            "好回答信号": q.get("good_answer_signal", "—"),
            "核验风险": q.get("risk_to_verify", "—"),
        } for q in questions]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("点击按钮后生成面试前问题。")


def _render_eval(result: dict | None) -> None:
    if not result:
        st.info("还没有面试评价。粘贴面试记录后点击“生成面试评价”。")
        return

    section("评价结论")
    form = result.get("form_filled") or {}
    stat_grid([
        {"label": "评级", "value": result.get("rating", "—")},
        {"label": "面试结论", "value": form.get("面试结论", "—")},
        {"label": "推荐动作", "value": form.get("推荐动作", "—")},
    ])

    section("维度打分")
    score_bars(list((result.get("dimension_scores") or {}).items()))

    section("面试纪要")
    st.write(result.get("summary", "—"))

    section("关注点")
    evidence_list(result.get("concerns") or [], "warning", "!", "暂无关注点")

    section("自动填写评价表")
    rows = [{"字段": k, "内容": v} for k, v in form.items()]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("查看 interview_eval JSON"):
        st.json(result)
