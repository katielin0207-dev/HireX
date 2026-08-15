"""AI 模拟面试页。

数字人渲染与 TTS 播报仍留在 main.py（它们和 Streamlit 的
components.v1 / 音频注入耦合），这里**通过参数注入**而不是反向 import ——
否则 main → views → main 会绕成循环导入。
"""
import streamlit as st

from app.i18n import t
from app.ui import (
    empty_state, page_header, pill, progress_steps, question_card,
    score_color, section, stat_grid,
)

def _steps():
    return [t("step.upload"), t("step.analyze"), t("step.interview"), t("step.report")]


def render(render_digital_human=None, speak=None) -> None:
    page_header(t("interview.title"), t("interview.subtitle"), "🤖")

    if not st.session_state.get("analysis_done"):
        progress_steps(_steps(), 0)
        empty_state(
            t("interview.need_analysis"),
            t("interview.need_analysis_desc"),
            "📄",
        )
        return

    progress_steps(_steps(), 2)
    if not st.session_state.get("interview_started"):
        _render_prep()
    else:
        _render_active(render_digital_human, speak)


def _render_prep() -> None:
    questions = st.session_state.get("all_questions") or []
    match = st.session_state.get("match_result") or {}
    jd_title = (st.session_state.get("jd_data") or {}).get("title", "未知岗位")
    score = match.get("overall_score", 0)

    stat_grid([
        {"label": t("analysis.target_role"), "value": jd_title},
        {"label": t("interview.qbank_total"), "value": t("analysis.q_count", n=len(questions))},
        {"label": t("interview.sample_n"), "value": t("analysis.q_count", n=st.session_state.n_rounds),
         "hint": t("interview.sample_hint")},
        {"label": t("interview.match"), "value": score, "color": score_color(score),
         "hint": match.get("recommendation", "")},
    ])

    st.markdown("")
    st.info(t("interview.brief", total=len(questions), n=st.session_state.n_rounds))

    with st.expander(t("interview.preview"), expanded=False):
        st.markdown(
            "".join(question_card(q, i + 1) for i, q in enumerate(questions[:9])),
            unsafe_allow_html=True,
        )
        if len(questions) > 9:
            st.caption(t("interview.preview_more", n=len(questions) - 9))

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if st.button(t("interview.start"), type="primary", use_container_width=True):
            from app.question_sampler import sample_questions_for_interview
            selected, remaining = sample_questions_for_interview(
                questions, st.session_state.n_rounds)
            st.session_state.selected_questions = selected
            st.session_state.remaining_pool = remaining
            st.session_state.interview_started = True
            st.rerun()


def _render_active(render_digital_human, speak) -> None:
    from app.interviewer import InterviewerAgent, InterviewState

    if st.session_state.get("interviewer") is None:
        with st.spinner(t("interview.booting")):
            try:
                agent = InterviewerAgent(
                    max_rounds=len(st.session_state.selected_questions) + 2)
                agent.load_parsed_data(st.session_state.jd_data, st.session_state.resume_data)
                agent.initialize_persona()
                agent.inject_questions(
                    st.session_state.selected_questions, st.session_state.remaining_pool)
                greeting, first_q = agent.generate_opening()
                st.session_state.interviewer = agent
                st.session_state.chat_messages = [
                    {"role": "interviewer", "content": greeting},
                    {"role": "interviewer", "content": first_q},
                ]
                if st.session_state.tts_enabled and speak:
                    speak(first_q)
                st.rerun()
            except Exception as e:                    # noqa: BLE001
                st.error(f'{t("interview.booting")} {e}')
                st.stop()

    agent = st.session_state.interviewer
    done = (agent.state in (InterviewState.REPORTING, InterviewState.DONE)
            or st.session_state.get("interview_done"))

    # ── 进度条 ────────────────────────────────
    pct = int(len(agent.turns) / agent.max_rounds * 100) if agent.max_rounds else 0
    meta = " · ".join([
        agent.persona.get("persona_name", "面试官"),
        agent.jd_data.get("title", "—"),
        t("interview.round", i=len(agent.turns), n=agent.max_rounds),
    ])
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        + pill(t("interview.running") if not done else t("interview.ended"),
               "brand" if not done else "success")
        + f'<span style="font-size:13px;color:var(--text-2)">{meta}</span></div>'
        f'<div class="br-track" style="height:6px;margin-bottom:16px">'
        f'<div class="br-fill" style="width:{pct}%;background:var(--brand)"></div></div>',
        unsafe_allow_html=True,
    )

    col_chat, col_side = st.columns([2.6, 1], gap="large")

    with col_side:
        if st.session_state.get("digital_human_enabled") and render_digital_human:
            last = next((m["content"] for m in reversed(st.session_state.chat_messages)
                         if m["role"] == "interviewer"), "")
            render_digital_human(last, agent.persona.get("persona_name", "面试官"))
        st.markdown("")
        st.markdown(
            f'<div class="kv"><span class="k">{t("interview.persona")}</span>'
            f'<span class="v">{agent.persona.get("persona_type", "balanced")}</span></div>'
            f'<div class="kv"><span class="k">{t("interview.covered")}</span>'
            f'<span class="v">{len(agent.covered_dimensions)}</span></div>'
            f'<div class="kv"><span class="k">{t("interview.remaining")}</span>'
            f'<span class="v">{len(agent.remaining_pool)}</span></div>'
            f'<div class="kv"><span class="k">{t("interview.pending")}</span>'
            f'<span class="v">{"、".join(agent.pending_dimensions[:2]) or "—"}</span></div>',
            unsafe_allow_html=True,
        )

    with col_chat:
        # ★ 改用 st.chat_message：原来是手搓 HTML 气泡塞进一个固定高度的
        #   div，长回答会被截断到 500 字且不能滚动。原生组件自带头像、
        #   自动换行与可选中文本。
        for msg in st.session_state.chat_messages:
            is_itv = msg["role"] == "interviewer"
            with st.chat_message("assistant" if is_itv else "user",
                                 avatar="🎓" if is_itv else "🙋"):
                st.markdown(msg["content"])

        if not done:
            answer = st.chat_input(t("interview.input_ph"))
            if answer and answer.strip():
                _handle_answer(answer.strip(), speak)
            if st.button(t("interview.end_btn"), use_container_width=True):
                closing = agent._generate_closing()
                st.session_state.chat_messages.append(
                    {"role": "interviewer", "content": closing})
                st.session_state.interview_done = True
                agent.state = InterviewState.REPORTING
                st.rerun()
        else:
            st.success(t("interview.done_msg"))
            if st.button(t("interview.view_report"), type="primary", use_container_width=True):
                _generate_report()


def _handle_answer(text: str, speak) -> None:
    from app.interviewer import InterviewState
    agent = st.session_state.interviewer
    st.session_state.chat_messages.append({"role": "candidate", "content": text})

    with st.spinner(t("interview.thinking")):
        result = agent.process_answer(text)

    msg = result.get("message", "")
    st.session_state.chat_messages.append({"role": "interviewer", "content": msg})
    if result.get("interview_ongoing"):
        if st.session_state.tts_enabled and msg and speak:
            speak(msg)
    else:
        st.session_state.interview_done = True
        agent.state = InterviewState.REPORTING
    st.rerun()


def _generate_report() -> None:
    from app.reporter import generate_report
    agent = st.session_state.interviewer
    try:
        st.session_state.report_data = generate_report(agent.get_interview_data())
        st.session_state.interview_done = True
        st.session_state.active_tab = "report"
        st.session_state.pop("_nav_radio", None)
    except Exception as e:                            # noqa: BLE001
        st.error(f"报告生成失败：{e}")
    st.rerun()
