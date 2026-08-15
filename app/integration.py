"""
集成 UI 模块：将 Harness/Checker/Skills/Flywheel 的可视化组件注入 Streamlit。
"""

import streamlit as st
import json
import os
from pathlib import Path
from .pipeline import RecruitmentPipeline, SkillsManager, create_pipeline
from .skills import SkillRegistry
from .flywheel import FlywheelStore

def render_skills_panel():
    """Skills 管理面板 — 浏览库 + 选择激活"""
    st.markdown("### Skills 库")
    # Cache manager in session_state to persist toggle state across rerenders
    if "_skills_manager" not in st.session_state:
        st.session_state._skills_manager = SkillsManager(skills_dir=str(Path(__file__).parent / "skills"))
    manager = st.session_state._skills_manager
    skills_data = manager.load()
    
    all_skills = skills_data.get("skills", [])
    active_skills = [s for s in all_skills if s["active"]]
    inactive_skills = [s for s in all_skills if not s["active"]]
    
    # Quick stats
    st.caption(f"{len(active_skills)} 已激活 / {len(inactive_skills)} 可用")
    
    # ── 已激活的 Skills ──
    if active_skills:
        st.markdown("**已激活**")
        for skill in active_skills:
            # 列宽 [2,5,1] → [1,5,2]：原来「ON」两个字占了 2 份，而按钮只有
            # 1 份。侧边栏本身就窄，1/8 折算下来只有十几像素宽，✕ 挤在里面
            # 既看不出居中也几乎点不中。ON 是个色块文字，1 份够用；按钮要 2 份。
            c1, c2, c3 = st.columns([1, 5, 2])
            with c1:
                st.markdown(
                    "<span style='color:#10b981;font-weight:700;font-size:12px'>ON</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(f"**{skill['name']}**  ")
                st.caption(f"{skill.get('description', '')[:50]}")
            with c3:
                # use_container_width 让按钮吃满这 2 份宽度 —— 不加的话
                # Streamlit 按内容宽度渲染，列再宽按钮还是那么小一颗。
                if st.button(
                    "停用",
                    key=f"sk_off_{skill['skill_id']}",
                    help=f"停用 {skill['name']}",
                    use_container_width=True,
                ):
                    manager.toggle(skill["skill_id"], False)
                    st.rerun()
    
    # ── 可用的 Skills 库 ──
    if inactive_skills:
        with st.expander(f"📚 可用 Skills ({len(inactive_skills)}个) — 按需激活", expanded=False):
            # Group by category
            cats = {}
            for s in inactive_skills:
                cat = s.get("category", "other")
                cats.setdefault(cat, []).append(s)
            
            cat_names = {
                "assessment": "📝 岗位题型", "screening": "🔍 筛选匹配", 
                "negotiation": "💬 谈判沟通", "compliance": "🛡 合规审查"
            }
            
            for cat, skills in cats.items():
                st.caption(cat_names.get(cat, cat))
                for skill in skills:
                    # 与「已激活」那组同样的列宽调整，理由见上。
                    c1, c2, c3 = st.columns([3, 4, 2])
                    with c1:
                        st.caption(skill["name"])
                    with c2:
                        st.caption(f"{skill.get('description', '')[:45]}...")
                    with c3:
                        if st.button(
                            "激活",
                            key=f"sk_on_{skill['skill_id']}",
                            help=f"激活 {skill['name']}",
                            use_container_width=True,
                        ):
                            manager.toggle(skill["skill_id"], True)
                            st.rerun()
    
    # ── 完整生命周期管理入口 ──
    # ★ 这里原本有个「➕ 自定义 Skill」表单，但它是坏的：
    #     sample = 'skill_id: "my-skill"\\nname: …'   ← 字面反斜杠 n
    #   文本框里显示的是一整行带 \n 的文本（1 行，不是 5 行），
    #   照着默认值点「安装到库」写出来的 skill.yaml 解析不出任何字段；
    #   解析那边 split('\\n') 切的同样是字面反斜杠 n。
    #   而且 delete / hot_reload 在 UI 上根本没有入口。
    #   现已整体搬到「🧩 Skills」独立页，六个操作齐全且有校验。
    st.caption("插入 / 卸载 / 热重载 / 组合视图 → 顶部「🧩 Skills」页")


def render_checker_panel(checker_results):
    """Checker 校准结果面板"""
    if not checker_results:
        return
    st.markdown("### Checker 校准结果")
    for i, cr in enumerate(checker_results):
        verdict = cr.get("verdict", "N/A")
        passed = cr.get("passed", False)
        scores = cr.get("scores", {})
        icon = "PASS" if passed else "FAIL"
        st.markdown(f"#### {'OK' if passed else 'XX'} Check #{i+1}: {verdict}")
        if scores:
            cols = st.columns(5)
            dims = ["数据准确性", "归因正确性", "格式合规", "维度覆盖", "幻觉检测"]
            for j, d in enumerate(dims):
                s = scores.get(d, 0)
                with cols[j]:
                    st.metric(d[:2], s)
        issues = cr.get("issues", [])
        if issues:
            for iss in issues[:5]:
                st.caption(f"[{iss.get('severity','?')}] {iss.get('dim','')}: {iss.get('desc','')[:80]}")
        st.divider()

def render_graph_panel(pipeline):
    """Graph DAG 可视化"""
    if not pipeline or not pipeline.graph:
        return
    st.markdown("### Graph DAG 执行状态")
    s = pipeline.graph.get_execution_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("节点", s.get("total_nodes", 0))
    c2.metric("成功", s.get("success", 0))
    c3.metric("失败", s.get("failed", 0))
    with st.expander("DAG 拓扑"):
        st.code(pipeline.get_graph_mermaid(), language="mermaid")

def render_flywheel_panel(flywheel_store=None):
    """飞轮统计"""
    if flywheel_store is None:
        flywheel_store = FlywheelStore()
    st.markdown("### Flywheel 飞轮统计 (Loop 3)")
    stats = flywheel_store.get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("历史记录", stats.get("total_records", 0))
    c2.metric("均分", f"{stats.get('avg_match_score',0):.0f}")
    c3.metric("标签", len(stats.get("recent_tags", [])))
    # ★ 检索后端如实显示。界面上写着"向量检索"而底下在跑关键词匹配，
    #   比降级本身糟糕得多 —— 那是假信号。
    backend_label = {
        "chroma": "ChromaDB",
        "vector": "内置向量索引",
        "keyword": "关键词匹配（降级）",
    }.get(stats.get("backend", ""), stats.get("backend", "?"))
    c4.metric("检索后端", backend_label)
    if stats.get("backend_note"):
        st.caption(stats["backend_note"])

def run_analysis_with_pipeline(jd_text, resume_text):
    """使用 Graph Pipeline 执行分析"""
    from .llm_client import llm_client
    skill_ids = st.session_state.get("active_skill_ids", [])
    pipeline = create_pipeline(llm_client=llm_client)
    pipeline.setup(jd_text=jd_text, resume_text=resume_text, active_skills=skill_ids, enable_checker=True, enable_flywheel=True)
    summary = pipeline.run()
    st.session_state.jd_data = summary.get("jd_data", {})
    st.session_state.resume_data = summary.get("resume_data", {})
    st.session_state.match_result = summary.get("match_result", {})
    st.session_state.all_questions = summary.get("questions", {}).get("questions", [])
    st.session_state.ambiguity_followups = summary.get("ambiguity_result", {})
    st.session_state.checker_results = summary.get("checker_results", [])
    st.session_state.graph_summary = summary.get("graph_summary", {})
    st.session_state.flywheel_stats = summary.get("flywheel_stats", {})
    st.session_state.skills_used = summary.get("skills_active", [])
    st.session_state.analysis_done = summary.get("success", False)
    st.session_state._pipeline = pipeline
    return summary
