"""参考实现模板：新模块页面的标准写法。

B/C/D/E 各新建自己的页面文件时，复制本文件改名后修改：
- views/analysis.py（B 简历筛选）
- views/risk.py（C 风险识别）
- views/interview_eval.py（D 面试评价，注意别和已有 interview.py 冲突）
- views/talent.py（E 人才评价）

然后在 app/main.py 的导航里注册（由 A 统一改，把函数名报给 A 即可）。

本模板演示四个标准动作：
1. 读共享数据（load_jd / list_candidates / load_candidate）
2. 调 LLM（call_llm，含 demo_mode 兜底）
3. 写回契约字段（update_candidate，只写自己负责的字段）
4. 页面布局（st.status 进度条，防止长任务看起来像卡死）
"""
import streamlit as st

from app.shared import (
    call_llm,
    list_candidates,
    load_candidate,
    update_candidate,
    load_jd,
    demo_mode_enabled,
    load_demo_cache,
)

# 本模块负责的契约字段（只允许写这一个字段，见 docs/CONTRACT.md 第2节）
MY_FIELD = "risk_report"  # ← 改成你的字段：match_result / risk_report / interview_eval

SYSTEM_PROMPT = """你是资深 HR 分析专家。只输出 JSON，不要输出其他内容。"""


def build_prompt(candidate: dict, jd: dict) -> str:
    """构造 LLM Prompt。这里放你的业务逻辑。"""
    return f"""请分析以下候选人：
【JD】{jd.get('raw_text', '')[:500]}
【简历解析】{candidate.get('resume_parsed', {})}

输出 JSON：{{"level": "低|中|高", "risks": [...], "interview_focus": [...]}}"""


def analyze(candidate: dict, jd: dict) -> dict:
    """核心业务函数：调 LLM 并返回结构化结果。含演示模式兜底。"""
    if demo_mode_enabled():
        cached = load_demo_cache("my_module")
        if cached is not None:
            st.info("演示模式：展示预跑缓存结果")
            return cached
    return call_llm(build_prompt(candidate, jd), system=SYSTEM_PROMPT, expect_json=True)


def render() -> None:
    """页面入口。main.py 导航注册的就是这个函数。"""
    st.header("模块名（改成你的）")

    # 1. 读共享数据
    jd = load_jd()
    candidates = list_candidates()
    if not jd or not candidates:
        st.warning("请先在「简历筛选」页上传 JD 和简历（或联系 A 检查 Mock 数据）")
        return

    # 2. 选择处理对象
    names = {c["id"]: c.get("name", c["id"]) for c in candidates}
    selected_id = st.selectbox("选择候选人", options=list(names), format_func=lambda x: names[x])
    candidate = load_candidate(selected_id)

    # 3. 触发分析（st.status 展示进度，避免长任务看似卡死——POC 踩过的坑）
    if st.button("开始分析", type="primary"):
        with st.status("分析中...", expanded=True) as status:
            st.write("调用 LLM 分析...")
            result = analyze(candidate, jd)
            # 4. 写回契约字段（只写自己负责的字段！）
            update_candidate(selected_id, MY_FIELD, result)
            status.update(label="分析完成", state="complete")
        st.success(f"已写入 {MY_FIELD}")

    # 5. 展示已有结果（页面刷新后也能看到）
    existing = candidate.get(MY_FIELD)
    if existing:
        st.subheader("分析结果")
        st.json(existing)
