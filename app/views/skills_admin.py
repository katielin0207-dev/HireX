"""Skills 管理页 —— 任务要求 C2 的六个生命周期操作，全部有 UI 入口。

要求原文（C2）：List / Insert / Activate / Compose / Delete / Hot Reload，
交付物里还明确写着演示视频要**重点展示「Skills 插入/激活/删除操作」**。

改造前的状况：`SkillRegistry` 里六个方法都实现了，但侧边栏面板只接了
激活/停用两个；`insert` 有个入口但是坏的（见下）；`delete` 和 `hot_reload`
根本没有入口。

★ 原 insert 为什么是坏的（已实测复现）：
    sample = 'skill_id: "my-skill"\\\\nname: "My Skill"\\\\n…'
  源码里写的是**字面反斜杠 n**，所以文本框里显示的是一整行
  `skill_id: "my-skill"\\nname: …`（1 行，不是 5 行）——
  照着默认值点「安装到库」，写进磁盘的 skill.yaml 是一行垃圾，
  `_parse_simple_yaml` 读不出任何字段。
  解析那边同样 `split('\\\\n')`，切的也是字面反斜杠 n。
"""
import os
import shutil
from pathlib import Path

import streamlit as st

from app.ui import empty_state, kv_row, page_header, pill, section

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

# 任务要求 C4 点名的 6 个预置 Skill —— 删掉它们会直接违反交付要求，
# 所以删除时要额外拦一道，而不是和自定义 Skill 一视同仁。
REQUIRED_PRESETS = {
    "tech-coding-test", "english-assessment", "culture-fit",
    "salary-negotiation", "campus-recruit", "executive-search",
}

TRIGGERS = ["on_question_generation", "on_matching", "on_interview_start"]
CATEGORIES = ["assessment", "screening", "negotiation", "compliance"]

SAMPLE_YAML = '''skill_id: "my-skill"
name: "我的自定义 Skill"
category: "assessment"
trigger: "on_question_generation"
description: "一句话说明这个 Skill 做什么"
depends_on: ["jd_data", "resume_data"]
produces: ["questions"]
active: false
'''

SAMPLE_PROMPT = """你是一位资深面试官。请基于以下信息生成 3 道面试题。

JD：{jd_data}
简历：{resume_data}
匹配结果：{match_result}

只输出 JSON：{{"questions": [{{"question": "...", "category": "技术基础", "difficulty": "中等", "intent": "..."}}]}}
"""


def _manager():
    """复用侧边栏那个实例 —— 两处必须是同一个 registry，
    否则在这里激活的 Skill，跑分析时用的是另一份状态。"""
    from app.pipeline import SkillsManager
    if "_skills_manager" not in st.session_state:
        st.session_state._skills_manager = SkillsManager(skills_dir=str(SKILLS_DIR))
    return st.session_state._skills_manager


def _parse_yaml_min(text: str) -> dict:
    """用 registry 自己的解析器，保证"这里能装进去 = 那边能读出来"。"""
    from app.skills.registry import SkillRegistry
    return SkillRegistry(str(SKILLS_DIR))._parse_simple_yaml(text)


def render() -> None:
    page_header("Skills 能力模块管理", "可插拔能力扩展层 · 列出 / 安装 / 激活 / 组合 / 卸载 / 热重载", "🧩")

    mgr = _manager()
    data = mgr.load()
    skills = data.get("skills", [])

    if not skills:
        empty_state("尚未加载到任何 Skill", f"检查目录：{SKILLS_DIR}", "🧩")
        return

    active = [s for s in skills if s["active"]]
    st.markdown(
        f'已安装 **{len(skills)}** 个 · 已激活 **{len(active)}** 个 · '
        f'预置必备 **{len(REQUIRED_PRESETS & {s["skill_id"] for s in skills})}/6**'
    )

    t_list, t_add, t_del, t_compose = st.tabs(
        ["📋 列出 / 激活", "📥 安装 (Insert)", "🗑 卸载 (Delete)", "🔗 组合 (Compose)"]
    )

    with t_list:
        _render_list(mgr, skills)
    with t_add:
        _render_insert(mgr)
    with t_del:
        _render_delete(mgr, skills)
    with t_compose:
        _render_compose(skills)


# ── List / Activate / Hot Reload ──────────────────────────────
def _render_list(mgr, skills) -> None:
    section("已安装的 Skill", "勾选即激活；改了磁盘上的 skill.yaml 后点「热重载」立即生效")

    q = st.text_input("筛选", placeholder="按 名称 / ID / 触发点 过滤…",
                      label_visibility="collapsed")
    cats = st.multiselect("按分类筛选", CATEGORIES, default=[], label_visibility="collapsed",
                          placeholder="按分类筛选（不选=全部）")

    rows = [
        s for s in skills
        if (not q or q.lower() in f'{s["skill_id"]}{s["name"]}{s["trigger"]}'.lower())
        and (not cats or s.get("category") in cats)
    ]
    if not rows:
        st.caption("没有匹配的 Skill")
        return

    rows.sort(key=lambda s: (not s["active"], s.get("category", ""), s["skill_id"]))
    st.caption(f"共 {len(rows)} 个")

    for s in rows:
        sid = s["skill_id"]
        c_tog, c_info, c_meta, c_rl = st.columns([0.9, 4.2, 2.4, 1.1])
        with c_tog:
            on = st.toggle("激活", value=s["active"], key=f"sk_tg_{sid}",
                           label_visibility="collapsed")
            if on != s["active"]:
                mgr.toggle(sid, on)
                st.rerun()
        with c_info:
            st.markdown(f'**{s["name"]}**　`{sid}`')
            st.caption(s.get("description", "")[:90] or "—")
        with c_meta:
            st.markdown(
                pill(s.get("category", "—"), "brand")
                + " " + pill(s.get("trigger", "—").replace("on_", ""), "neutral")
                + (" " + pill("预置", "success") if sid in REQUIRED_PRESETS else ""),
                unsafe_allow_html=True,
            )
        with c_rl:
            if st.button("热重载", key=f"sk_rl_{sid}", help="重新读取磁盘上的 skill.yaml"):
                updated = mgr.registry.hot_reload(sid)
                if updated:
                    st.success(f"{updated.name} 已重载", icon="✅")
                else:
                    st.error("重载失败：找不到源文件")
        st.divider()


# ── Insert ────────────────────────────────────────────────────
def _render_insert(mgr) -> None:
    section("安装新 Skill", "写 YAML + Prompt 模板，落盘后注册进 Graph")

    col_y, col_p = st.columns(2, gap="large")
    with col_y:
        st.caption("skill.yaml")
        yaml_text = st.text_area("skill.yaml", value=SAMPLE_YAML, height=260,
                                 label_visibility="collapsed")
    with col_p:
        st.caption("prompt_template.txt　（可用 {jd_data} / {resume_data} / {match_result} 占位）")
        prompt_text = st.text_area("prompt", value=SAMPLE_PROMPT, height=260,
                                   label_visibility="collapsed")

    # ★ 先校验再落盘。原来的实现是"直接写文件再 rerun"，
    #   写坏了要到下次加载才发现，而且坏文件已经躺在 skills/ 里了。
    parsed = {}
    problems = []
    try:
        parsed = _parse_yaml_min(yaml_text)
    except Exception as e:                                # noqa: BLE001
        problems.append(f"YAML 解析失败：{e}")

    sid = str(parsed.get("skill_id", "")).strip()
    if not sid:
        problems.append("缺少 skill_id")
    elif not all(c.isalnum() or c in "-_" for c in sid):
        problems.append(f"skill_id 只能用字母/数字/-/_，当前：{sid}")
    if not str(parsed.get("name", "")).strip():
        problems.append("缺少 name")
    trig = str(parsed.get("trigger", "")).strip()
    if trig not in TRIGGERS:
        problems.append(f"trigger 必须是 {TRIGGERS} 之一，当前：{trig or '(空)'}")
    if sid and (SKILLS_DIR / sid).exists():
        problems.append(f"目录已存在：skills/{sid}（想改用「热重载」）")
    if "{" not in prompt_text:
        problems.append("Prompt 模板里没有任何 {占位符}，Skill 拿不到 JD/简历数据")

    if problems:
        for p in problems:
            st.warning(p, icon="⚠️")
    else:
        st.success(f"校验通过：{parsed.get('name')}（{sid}）→ {trig}", icon="✅")

    if st.button("📥 安装到 Skills 库", type="primary", disabled=bool(problems),
                 use_container_width=True):
        target = SKILLS_DIR / sid
        try:
            target.mkdir(parents=True, exist_ok=False)
            (target / "skill.yaml").write_text(yaml_text, encoding="utf-8")
            (target / "prompt_template.txt").write_text(prompt_text, encoding="utf-8")
            # ★ 走 registry.insert 而不是只写文件 —— 只写文件的话当前进程的
            #   registry 里没有它，要重启才认得，"热插拔"就名不副实了。
            skill = mgr.registry.insert(str(target))
            if skill:
                st.success(f"已安装 {skill.name}（默认关闭，去「列出 / 激活」里打开）", icon="🎉")
                st.rerun()
            st.error("落盘成功但注册失败，请检查 YAML 字段")
        except Exception as e:                            # noqa: BLE001
            shutil.rmtree(target, ignore_errors=True)     # 装了一半要回滚，别留半个目录
            st.error(f"安装失败（已回滚）：{e}")


# ── Delete ────────────────────────────────────────────────────
def _render_delete(mgr, skills) -> None:
    section("卸载 Skill", "从 Graph 中移除；可选择是否连磁盘目录一并删除")

    ids = [s["skill_id"] for s in skills]
    sid = st.selectbox("选择要卸载的 Skill", ids,
                       format_func=lambda i: next(
                           f'{s["name"]}（{i}）' for s in skills if s["skill_id"] == i))
    target = next(s for s in skills if s["skill_id"] == sid)
    kv_row([
        ("名称", target["name"]), ("分类", target.get("category", "—")),
        ("触发点", target.get("trigger", "—")),
        ("当前状态", "已激活" if target["active"] else "未激活"),
    ])

    if sid in REQUIRED_PRESETS:
        st.warning(
            f"`{sid}` 是任务要求 C4 点名的 6 个预置 Skill 之一。"
            "删掉它会直接违反交付要求（自带至少 6 个预置 Skill），确认你是有意为之。",
            icon="⚠️",
        )

    hard = st.checkbox("同时删除磁盘目录 skills/" + sid + "（不可恢复）")
    confirm = st.checkbox(f"我确认卸载 {sid}")

    if st.button("🗑 执行卸载", disabled=not confirm, use_container_width=True):
        res = mgr.delete(sid)
        if not res.get("success"):
            st.error("从注册表移除失败")
            return
        if hard:
            try:
                shutil.rmtree(SKILLS_DIR / sid)
            except Exception as e:                        # noqa: BLE001
                st.error(f"已从 Graph 移除，但目录删除失败：{e}")
                st.rerun()
        # ★ 只从注册表移除的话，下次新建 SkillsManager 会重新扫描目录、它又回来了。
        #   这里把话说清楚，免得被当成"删除没生效"。
        st.success(
            f"已卸载 {sid}" + ("（目录已删除）" if hard
                              else "（仅本次会话；重启后会重新从磁盘扫描到）"),
            icon="✅",
        )
        st.rerun()


# ── Compose ───────────────────────────────────────────────────
def _render_compose(skills) -> None:
    section("Skill 与 Graph 的融合", "同一 trigger 下的已激活 Skill 会在 Graph 中并行执行，产出交给 Skill Merger 合并")

    for trig in TRIGGERS:
        on = [s for s in skills if s["active"] and s.get("trigger") == trig]
        off = [s for s in skills if not s["active"] and s.get("trigger") == trig]
        st.markdown(f'**`{trig}`**　已激活 {len(on)} / 共 {len(on) + len(off)}')
        if on:
            st.markdown(
                " ".join(pill(s["name"], "success") for s in on), unsafe_allow_html=True)
            st.code(
                "[上游节点] ──trigger: %s\n" % trig
                + "\n".join(f"    ├── [Skill: {s['skill_id']}]" for s in on[:-1])
                + (f"\n    └── [Skill: {on[-1]['skill_id']}]" if on else "")
                + "\n            ↓\n    [Skill Merger] → 合并产出\n            ↓\n    [Checker Agent] → 校验合并后输出",
                language=None,
            )
        else:
            st.caption("该触发点下没有已激活的 Skill，Graph 中不会插入节点")
        st.divider()

    st.info(
        "并行是真的并行：`pipeline._fn_execute_skills` 用 ThreadPoolExecutor 同时发起，"
        "耗时等于最慢的那一个，而不是逐个相加。",
        icon="ℹ️",
    )
