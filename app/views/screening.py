"""简历筛选模块（MVP 模块一，由 A 负责）。

功能闭环（对应业务需求）：
  1. JD：粘贴/上传 → 自动结构化 → HR/用人部门在线编辑任职要求 + 调整匹配权重
  2. 简历库：从 mock 简历库批量导入 + 支持新上传，LLM 解析为结构化字段
  3. 批量筛选：硬性条件规则引擎（确定性，零波动）+ 软性素质 LLM 评分
              → 0-100 匹配度（区分硬性分/软性分）→ 写回契约字段 match_result
  4. 排名表：全部候选人按总分排序，硬性/软性/总分一目了然
  5. 用人部门审核：逐份查看匹配评价 → 通过/不通过 + 备注 → 通过者推送 HR 电话初面

设计要点（来自 POC 教训）：
  - 硬性条件（学历/年限/证书）用【规则引擎代码】算，LLM 只评软性素质，
    从根本上消除 POC 发现的"学历分在 85/100 间波动"问题。
  - 软性评分用 map_llm 并发（默认 3 并发），10 份简历不再串行跑 20 分钟。
  - 长任务用 st.status 展示进度，避免页面看似卡死。
  - 演示模式：实跑一次后缓存，演示时切 demo 直接读缓存，不依赖 API。

本模块只写契约里的这些字段：resume_parsed、match_result、status、tags。
读取 jd（load_jd）和候选人文件，不 import 其他模块。
"""
import os
import re
import streamlit as st

from app.shared import (
    call_llm,
    map_llm,
    save_candidate,
    load_candidate,
    update_candidate,
    list_candidates,
    save_jd,
    load_jd,
    demo_mode_enabled,
    load_demo_cache,
    save_demo_cache,
)

# 简历库目录（A 提供的 mock 数据，已提交 git）
RESUMES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mock", "resumes",
)

# 学历等级映射（用于硬性规则引擎）
_DEGREE_LEVEL = {"大专": 0, "本科": 1, "硕士": 2, "研究生": 2, "博士": 3, "博士后": 4}

SYSTEM_JD = "你是资深 HR 招聘专家，善于把岗位描述拆解为结构化任职要求。只输出 JSON。"
SYSTEM_PARSE = "你是简历解析专家，提取简历关键信息为结构化 JSON。只输出 JSON。"
SYSTEM_SOFT = "你是资深技术招聘专家，评估候选人与岗位的软性素质匹配。只输出 JSON。"


# ────────────────────────────────────────────────────────────
# 1. JD 结构化
# ────────────────────────────────────────────────────────────
def parse_jd(raw_text: str) -> dict:
    """把 JD 原文解析为结构化任职要求。"""
    prompt = f"""请解析以下岗位 JD，输出结构化 JSON：
{raw_text}

输出格式：
{{
  "title": "岗位名称",
  "hard": {{
    "degree": "本科|硕士|博士|大专",
    "min_years": 数字(最低工作年限，无明确要求填0),
    "must_skills": ["必备技能1","必备技能2"],
    "nice_skills": ["加分技能1"]
  }},
  "soft": ["软实力要求1","软实力要求2"]
}}"""
    return call_llm(prompt, system=SYSTEM_JD, expect_json=True)


def render_jd_section():
    """JD 输入 / 结构化 / 编辑 / 权重。"""
    st.subheader("① 岗位 JD 与筛选要求")

    jd = load_jd() or {}
    default_text = jd.get("raw_text", "")
    raw = st.text_area(
        "粘贴或编辑岗位 JD",
        value=default_text,
        height=160,
        placeholder="例如：招聘 Python 后端开发工程师，3年以上经验，熟悉 FastAPI/Django...",
        key="jd_text_input",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("🔧 生成结构化任职要求", type="primary", key="gen_jd"):
            if not raw.strip():
                st.warning("请先填写 JD 内容")
            else:
                with st.status("解析 JD 中...", expanded=True) as s:
                    s.write("调用 LLM 拆解任职要求...")
                    req = parse_jd(raw)
                    save_jd({"title": req.get("title", "岗位"), "raw_text": raw,
                             "requirements": req})
                    s.update(label="JD 已结构化", state="complete")
                st.success("已生成结构化任职要求，可在下方调整")
                st.rerun()

    # 已结构化的任职要求 → 可编辑
    req = (jd or {}).get("requirements")
    hard_w, soft_w = 0.6, 0.4
    if req:
        st.markdown("**任职要求（可编辑）**")
        h = req.get("hard", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            h["degree"] = st.text_input("学历要求", value=h.get("degree", "本科"))
        with c2:
            h["min_years"] = st.number_input("最低年限", min_value=0,
                                             value=int(h.get("min_years", 3)))
        with c3:
            soft_input = st.text_input(
                "软实力(逗号分隔)", value="，".join(req.get("soft", [])))
            req["soft"] = [x.strip() for x in soft_input.split("，") if x.strip()]
        h["must_skills"] = [x.strip() for x in st.text_input(
            "必备技能(逗号分隔)", value="，".join(h.get("must_skills", []))
        ).split("，") if x.strip()]
        h["nice_skills"] = [x.strip() for x in st.text_input(
            "加分技能(逗号分隔)", value="，".join(h.get("nice_skills", []))
        ).split("，") if x.strip()]

        hard_w = st.slider("硬性条件权重", 0.0, 1.0, 0.6, 0.05, key="hard_w")
        soft_w = round(1.0 - hard_w, 2)
        st.caption(f"当前权重：硬性 {hard_w:.0%} / 软性 {soft_w:.0%}")

        if st.button("💾 保存任职要求", key="save_req"):
            save_jd({"title": jd.get("title", "岗位"), "raw_text": raw,
                     "requirements": req, "weights": {"hard": hard_w, "soft": soft_w}})
            st.success("已保存")

    return hard_w, soft_w


# ────────────────────────────────────────────────────────────
# 2. 简历库导入与解析
# ────────────────────────────────────────────────────────────
def _infer_name(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0]
    # 去掉 "01_" 前缀和 "_优秀/_风险..." 后缀
    m = re.match(r"^\d+[_-]?(.*?)(_优秀|_中等|_风险.*)?$", base)
    return m.group(1) if m else base


def parse_resume(text: str) -> dict:
    """LLM 把简历原文解析为结构化字段。"""
    prompt = f"""请解析以下简历，输出结构化 JSON：
{text[:3000]}

输出格式：
{{
  "name": "姓名",
  "education": [{{"school":"学校","degree":"本科|硕士|博士|大专","major":"专业","start":"2018.09","end":"2022.06"}}],
  "experience": [{{"company":"公司","title":"职位","start":"2022.07","end":"至今"}}],
  "skills": ["技能1","技能2"],
  "total_years": 数字(累计工作年限，按经历估算)
}}"""
    return call_llm(prompt, system=SYSTEM_PARSE, expect_json=True)


def render_resume_library():
    """从 mock 库批量导入 + 新上传，解析后写入候选人文件。"""
    st.subheader("② 简历库导入")

    files = sorted(f for f in os.listdir(RESUMES_DIR) if f.endswith(".txt"))
    options = {f: _infer_name(f) for f in files}
    selected = st.multiselect(
        "选择简历库中的简历（默认全选）",
        options=list(options.keys()),
        default=list(options.keys()),
        format_func=lambda f: options[f],
    )

    uploaded = st.file_uploader(
        "或上传新简历（.txt）", type=["txt"], accept_multiple_files=True,
        key="upload_resumes")
    if uploaded:
        for u in uploaded:
            path = os.path.join(RESUMES_DIR, u.name)
            with open(path, "wb") as f:
                f.write(u.getbuffer())
        st.success(f"已暂存 {len(uploaded)} 份上传简历，点下方按钮一并导入")
        files = sorted(f for f in os.listdir(RESUMES_DIR) if f.endswith(".txt"))
        options = {f: _infer_name(f) for f in files}
        for f in uploaded:
            if f.name not in selected:
                selected = selected + [f.name]

    if st.button("📥 导入并解析选中简历", type="primary", key="import_resumes"):
        if not selected:
            st.warning("请至少选择一份简历")
            return
        targets = [f for f in selected if f in options]
        with st.status(f"解析 {len(targets)} 份简历中...", expanded=True) as s:
            def _do_parse(fname):
                with open(os.path.join(RESUMES_DIR, fname), encoding="utf-8") as fh:
                    txt = fh.read()
                parsed = parse_resume(txt)
                name = parsed.get("name") or options[fname]
                cid = "cand_" + re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", name)[:8]
                cand = {
                    "id": cid,
                    "name": name,
                    "resume_text": txt,
                    "resume_file": os.path.join("mock", "resumes", fname),
                    "resume_parsed": parsed,
                    "status": "new",
                    "tags": parsed.get("skills", []),
                }
                save_candidate(cand)
                return name

            results = map_llm(targets, _do_parse, max_workers=3)
            ok = [r for r in results if not isinstance(r, dict) or "error" not in r]
            s.write(f"成功导入 {len(ok)}/{len(targets)} 份")
            s.update(label="简历库导入完成", state="complete")
        st.success(f"已导入 {len(ok)} 份简历到候选人库")
        st.rerun()


# ────────────────────────────────────────────────────────────
# 3. 硬性条件规则引擎（确定性，零波动）
# ────────────────────────────────────────────────────────────
def _degree_level(d: str) -> int:
    if not d:
        return 0
    for k, v in _DEGREE_LEVEL.items():
        if k in d:
            return v
    return 0


def hard_rule_engine(req_hard: dict, parsed: dict):
    """返回 (degree_score, years_score, skills_score, skills_detail)。"""
    # 学历（硬性门槛：不满足直接 0 分，并在 run_screening 中触发否决）
    req_deg = _degree_level(req_hard.get("degree", ""))
    cand_deg = max([_degree_level(e.get("degree", "")) for e in parsed.get("education", [])] or [0])
    if cand_deg >= req_deg:
        degree_score = 100
    else:
        degree_score = 0
    degree_reason = (f"要求{req_hard.get('degree','-')}，候选人最高{cand_deg}级"
                     + ("（不满足，硬性不通过）" if req_deg and degree_score == 0 else ""))

    # 年限
    min_y = float(req_hard.get("min_years", 0) or 0)
    cand_y = float(parsed.get("total_years", 0) or 0)
    if min_y <= 0:
        years_score = 100
        years_reason = "无年限要求"
    elif cand_y >= min_y:
        years_score = 100
        years_reason = f"要求{min_y}年，候选人{cand_y}年"
    else:
        years_score = int(min(100, cand_y / min_y * 100))
        years_reason = f"要求{min_y}年，候选人仅{cand_y}年（{years_score}分）"

    # 技能
    must = [s.lower() for s in req_hard.get("must_skills", [])]
    cand_sk = [s.lower() for s in parsed.get("skills", [])]
    matched, missing = [], []
    for m in must:
        hit = any(m in c or c in m for c in cand_sk)
        (matched if hit else missing).append(m)
    if must:
        skills_score = int(len(matched) / len(must) * 100)
    else:
        skills_score = 100
    skills_reason = (f"必备技能命中 {len(matched)}/{len(must)}"
                     + (f"，缺失：{', '.join(missing)}" if missing else "，全部命中"))

    return degree_score, years_score, skills_score, {
        "matched": matched, "missing": missing,
        "degree_reason": degree_reason, "years_reason": years_reason,
        "skills_reason": skills_reason,
    }


# ────────────────────────────────────────────────────────────
# 4. 软性素质 LLM 评分
# ────────────────────────────────────────────────────────────
def soft_score(jd: dict, parsed: dict) -> dict:
    """LLM 评估软性素质匹配，返回 {soft_score, matched_points, gap_points, summary}。"""
    soft_req = jd.get("requirements", {}).get("soft", [])
    prompt = f"""请评估候选人与岗位的【软性素质】匹配度（不含硬性技能，硬性由规则引擎单独计算）。

【岗位软性要求】{soft_req}
【候选人简历要点】
- 工作经历：{parsed.get('experience', [])}
- 技能：{parsed.get('skills', [])}
- 项目：见简历原文

输出 JSON：
{{
  "soft_score": 0-100的整数,
  "matched_points": ["软性匹配点1"],
  "gap_points": ["软性差距点1"],
  "summary": "一句话总结软性匹配情况"
}}"""
    return call_llm(prompt, system=SYSTEM_SOFT, expect_json=True)


# ────────────────────────────────────────────────────────────
# 5. 批量筛选主流程
# ────────────────────────────────────────────────────────────
def run_screening(jd: dict, hard_w: float, soft_w: float):
    """对全部候选人执行硬性规则 + 软性 LLM 评分，写回 match_result。"""
    req_hard = jd.get("requirements", {}).get("hard", {})
    candidates = list_candidates()

    # 硬性（同步，快）
    hard_map = {}
    for c in candidates:
        d, y, sk, det = hard_rule_engine(req_hard, c.get("resume_parsed", {}))
        hard_map[c["id"]] = (d, y, sk, det)

    # 软性（并发 LLM）
    def _score(c):
        return soft_score(jd, c.get("resume_parsed", {}))

    soft_results = map_llm(candidates, _score, max_workers=3)

    # 合并写回
    for c, sr in zip(candidates, soft_results):
        d, y, sk, det = hard_map[c["id"]]
        if isinstance(sr, dict) and "error" in sr:
            soft_s, mp, gp, summ = 0, [], [f"软性评分失败：{sr['error']}"], "软性评分未完成"
        else:
            soft_s = int(sr.get("soft_score", 0))
            mp = sr.get("matched_points", [])
            gp = sr.get("gap_points", [])
            summ = sr.get("summary", "")

        hard_s = round(0.3 * d + 0.3 * y + 0.4 * sk)
        overall = round(hard_s * hard_w + soft_s * soft_w)

        # 一票否决：硬性基础分过低 / 学历门槛不满足 直接不推进
        deg_fail = (req_hard.get("degree") and d == 0)
        if hard_s < 50 or deg_fail:
            rec = "不推进"
        elif overall >= 80:
            rec = "推进"
        elif overall >= 60:
            rec = "待定"
        else:
            rec = "不推进"

        # 综合匹配点/差距点：硬性缺失技能也进差距点
        gap = list(gp)
        if det["missing"]:
            gap.append(f"硬性技能缺失：{', '.join(det['missing'])}")

        match_result = {
            "overall_score": overall,
            "hard_score": hard_s,
            "soft_score": soft_s,
            "recommendation": rec,
            "breakdown": {
                "education_match": {"score": d, "reason": det["degree_reason"]},
                "experience_match": {"score": y, "reason": det["years_reason"]},
                "skills_match": {"score": sk, "reason": det["skills_reason"]},
                "project_relevance": {"score": soft_s, "reason": summ},
            },
            "matched_points": mp,
            "gap_points": gap,
            "summary": summ,
        }
        update_candidate(c["id"], "match_result", match_result)

    # 演示缓存（实跑一次后，演示模式可直接读）
    cache = {c["id"]: c.get("match_result") for c in list_candidates()
             if c.get("match_result")}
    save_demo_cache("screening_batch", cache)
    return len(candidates)


def render_screening():
    """触发批量筛选 + 排名表 + 用人部门审核。"""
    jd = load_jd()
    candidates = list_candidates()
    if not jd or not jd.get("requirements"):
        st.warning("请先在 ① 中生成并保存结构化 JD")
        return
    if not candidates:
        st.warning("请先在 ② 中导入简历")
        return

    weights = jd.get("weights", {"hard": 0.6, "soft": 0.4})
    hard_w, soft_w = weights["hard"], weights["soft"]

    st.subheader("③ 批量筛选")
    if st.button("🚀 开始筛选（硬性规则 + 软性 LLM）", type="primary", key="run_screen"):
        if demo_mode_enabled():
            cached = load_demo_cache("screening_batch")
            if cached:
                with st.status("演示模式：加载缓存结果", expanded=True) as s:
                    for cid, mr in cached.items():
                        update_candidate(cid, "match_result", mr)
                    s.update(label="已加载缓存", state="complete")
                st.info("演示模式：使用预跑缓存，未调用 API")
            else:
                st.warning("演示缓存为空，先用正常模式实跑一次")
        else:
            with st.status("筛选中（硬性规则同步 + 软性并发 LLM）...", expanded=True) as s:
                n = run_screening(jd, hard_w, soft_w)
                s.write(f"已完成 {n} 位候选人的匹配评分")
                s.update(label="筛选完成", state="complete")
            st.success(f"已为 {n} 位候选人生成匹配评价")
        st.rerun()

    # 排名表
    ranked = sorted(
        [c for c in candidates if c.get("match_result")],
        key=lambda c: c["match_result"]["overall_score"], reverse=True)
    if ranked:
        st.subheader("④ 候选人匹配排名")
        rows = []
        for c in ranked:
            mr = c["match_result"]
            rows.append({
                "姓名": c.get("name", c["id"]),
                "硬性分": mr["hard_score"],
                "软性分": mr["soft_score"],
                "总分": mr["overall_score"],
                "推荐": mr["recommendation"],
                "状态": c.get("status", "new"),
            })
        df = __import__("pandas").DataFrame(rows)
        # 颜色：总分>=80绿 60-79黄 <60红
        def _color(v):
            return ("background-color: #dcfce7" if v >= 80
                    else "background-color: #fef9c3" if v >= 60
                    else "background-color: #fee2e2")
        styled = df.style.map(_color, subset=["总分"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # 用人部门审核
        st.subheader("⑤ 用人部门审核与推送")
        st.caption("查看匹配评价后，选择是否通过筛选；通过者将推送 HR 进行电话初面。")
        for c in ranked:
            mr = c["match_result"]
            with st.expander(f"{c.get('name')} — 总分 {mr['overall_score']}（{mr['recommendation']}）"):
                st.markdown(f"**匹配总结**：{mr.get('summary','')}")
                col_m, col_g = st.columns(2)
                with col_m:
                    st.markdown("**匹配点**")
                    for p in mr.get("matched_points", []):
                        st.markdown(f"- OK {p}")
                with col_g:
                    st.markdown("**差距点**")
                    for g in mr.get("gap_points", []):
                        st.markdown(f"- 注意 {g}")
                st.markdown("**维度明细**")
                for k, v in mr.get("breakdown", {}).items():
                    st.markdown(f"- {k}：{v['score']} 分 — {v['reason']}")

                note_key = f"note_{c['id']}"
                decision = st.radio(
                    "用人部门审核", ["待审核", "通过筛选", "不通过"],
                    index=["待审核", "通过筛选", "不通过"].index(
                        c.get("screen_decision", "待审核")),
                    key=f"dec_{c['id']}", horizontal=True)
                note = st.text_area("审核备注（推送给 HR）",
                                    value=c.get("screen_note", ""), key=note_key)

                if st.button("提交审核", key=f"submit_{c['id']}"):
                    upd = {"screen_decision": decision, "screen_note": note}
                    if decision == "通过筛选":
                        upd["status"] = "screened"
                        upd["tags"] = c.get("tags", []) + ["已通过筛选"]
                    cand = load_candidate(c["id"])
                    cand.update(upd)
                    save_candidate(cand)
                    if decision == "通过筛选":
                        st.success("已通过筛选，简历及匹配评价已推送给 HR 进行电话初面")
                    else:
                        st.info(f"已记录：{decision}")
                    st.rerun()

                sync_col, interview_col = st.columns(2)
                with sync_col:
                    if st.button("同步到智能分析", key=f"sync_risk_{c['id']}", use_container_width=True):
                        cand = load_candidate(c["id"])
                        cand["status"] = "screened"
                        cand["screen_decision"] = cand.get("screen_decision", "通过筛选")
                        cand["tags"] = list(dict.fromkeys((cand.get("tags") or []) + ["已同步智能分析"]))
                        save_candidate(cand)
                        st.session_state["risk_selected_candidate"] = c["id"]
                        st.session_state["selected_candidate_id"] = c["id"]
                        st.session_state["active_tab"] = "risk"
                        st.session_state["_nav_radio"] = "risk"
                        st.rerun()
                with interview_col:
                    if st.button("进入 AI 面试", key=f"sync_interview_{c['id']}", use_container_width=True):
                        cand = load_candidate(c["id"])
                        cand["status"] = "interview_pack_ready"
                        cand["tags"] = list(dict.fromkeys((cand.get("tags") or []) + ["待生成面试评价"]))
                        save_candidate(cand)
                        st.session_state["selected_candidate_id"] = c["id"]
                        st.session_state["risk_selected_candidate"] = c["id"]
                        st.session_state["active_tab"] = "interview_eval"
                        st.session_state["_nav_radio"] = "interview_eval"
                        st.rerun()


# ────────────────────────────────────────────────────────────
# 页面入口
# ────────────────────────────────────────────────────────────
def render():
    st.header("简历筛选（AI 智能甄选）")
    render_jd_section()
    st.divider()
    render_resume_library()
    st.divider()
    render_screening()
