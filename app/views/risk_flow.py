"""风险模块统一入口：简历风险识别与录用前核验。"""

import streamlit as st

from app.views import preoffer, risk


def render() -> None:
    pending = st.session_state.pop("_hirex_pending_risk_stage", None)
    if pending in ("简历风险识别", "录用前核验"):
        st.session_state["risk_stage"] = pending

    stage = st.segmented_control(
        "风险流程",
        options=["简历风险识别", "录用前核验"],
        default="简历风险识别",
        key="risk_stage",
        label_visibility="collapsed",
    )
    st.caption("前置识别简历疑点；确定拟录用人选后，再完成背调与资质核验。")

    if stage == "简历风险识别":
        risk.render()
    else:
        preoffer.render()
