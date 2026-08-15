"""模块一统一入口：岗位 JD 生成与简历筛选。"""

import streamlit as st

from app.views import interview_eval, job_posting, screening


def render() -> None:
    pending = st.session_state.pop("_hirex_pending_screening_stage", None)
    if pending in ("岗位 JD", "简历筛选", "面试辅助"):
        st.session_state["screening_stage"] = pending

    stage = st.segmented_control(
        "模块一流程",
        options=["岗位 JD", "简历筛选", "面试辅助"],
        default="岗位 JD",
        key="screening_stage",
        label_visibility="collapsed",
    )
    st.caption("岗位标准 → 批量筛选 → 候选人专属 9 题与面试评价，统一在一个工作区完成。")

    if stage == "岗位 JD":
        job_posting.render()
    elif stage == "简历筛选":
        screening.render()
    else:
        interview_eval.render()
