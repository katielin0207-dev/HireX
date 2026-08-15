"""简历筛选模块（MVP 模块一，由 A 负责）。

单页流程：
  1. 顶部两级下拉选岗位（岗位范围 → 具体岗位），按「选定」确认
  2. 展示岗位 JD 摘要 / 权重 / 分数线
  3. 开始筛选 → 卡片式排名与审核（候选人库预先置于 sessions/candidates/）

数据模型：
  - 岗位定义：mock/haixin_jobs.json（后续接爬虫）
  - 候选人：sessions/candidates/*.json（共享库）
  - 匹配结果：candidate["matched_jobs"][job_id] = {...}，
              一份简历可保留对多个岗位的匹配记录，切岗位不覆盖。
"""
import streamlit as st

from app.shared import (
    call_llm,
    map_llm,
    save_candidate,
    load_candidate,
    list_candidates,
)
from app.shared.job_utils import (
    _WEIGHT_DIMS,
    _DIM_LABEL,
    _DEGREE_LEVEL,
    _normalize_weights,
)
from app.shared.jobs import (
    load_job, jobs_in_category, JOB_CATEGORIES,
)
from app.ui import section
from app.ui.theme import score_tone, TOKENS


SYSTEM_SOFT = "你是资深技术招聘专家，评估候选人与岗位的软性素质匹配。只输出 JSON。"


# ────────────────────────────────────────────────────────────
# 辅助
# ────────────────────────────────────────────────────────────
def _degree_level(d: str) -> int:
    if not d:
        return 0
    for k, v in _DEGREE_LEVEL.items():
        if k in d:
            return v
    return 0


def _get_match(c: dict, job_id: str):
    return (c.get("matched_jobs") or {}).get(job_id)


# ────────────────────────────────────────────────────────────
# LLM
# ────────────────────────────────────────────────────────────
def soft_score(job: dict, parsed: dict) -> dict:
    soft_req = job.get("soft", [])
    prompt = f"""请评估候选人与岗位的【软性素质】匹配度（不含硬性技能，硬性由规则引擎单独计算）。

【岗位软性要求】{soft_req}
【候选人简历要点】
- 工作经历：{parsed.get('experience', [])}
- 技能：{parsed.get('skills', [])}

输出 JSON：
{{
  "soft_score": 0-100的整数,
  "matched_points": ["软性匹配点1"],
  "gap_points": ["软性差距点1"],
  "summary": "一句话总结软性匹配情况"
}}"""
    return call_llm(prompt, system=SYSTEM_SOFT, expect_json=True)


# ────────────────────────────────────────────────────────────
# 硬性规则引擎
# ────────────────────────────────────────────────────────────
def hard_rule_engine(req_hard: dict, parsed: dict):
    req_deg = _degree_level(req_hard.get("degree", ""))
    cand_deg = max([_degree_level(e.get("degree", "")) for e in parsed.get("education", [])] or [0])
    degree_score = 100 if cand_deg >= req_deg else 0
    degree_reason = (f"要求{req_hard.get('degree','-')}，候选人最高{cand_deg}级"
                     + ("（不满足，硬性不通过）" if req_deg and degree_score == 0 else ""))

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

    must = [s.lower() for s in req_hard.get("must_skills", [])]
    cand_sk = [s.lower() for s in parsed.get("skills", [])]
    matched, missing = [], []
    for m in must:
        hit = any(m in c or c in m for c in cand_sk)
        (matched if hit else missing).append(m)
    skills_score = int(len(matched) / len(must) * 100) if must else 100
    skills_reason = (f"必备技能命中 {len(matched)}/{len(must)}"
                     + (f"，缺失：{', '.join(missing)}" if missing else "，全部命中"))

    return degree_score, years_score, skills_score, {
        "matched": matched, "missing": missing,
        "degree_reason": degree_reason, "years_reason": years_reason,
        "skills_reason": skills_reason,
    }


# ────────────────────────────────────────────────────────────
# 批量筛选主流程（per-job，写到 candidate["matched_jobs"][job_id]）
# ────────────────────────────────────────────────────────────
def run_screening(job: dict, weights: dict, thresholds: dict) -> int:
    job_id = job["id"]
    req_hard = job.get("hard", {})
    th_pass = int(thresholds.get("pass", 80))
    th_hold = int(thresholds.get("hold", 60))
    candidates = list_candidates()

    hard_map = {}
    for c in candidates:
        d, y, sk, det = hard_rule_engine(req_hard, c.get("resume_parsed", {}))
        hard_map[c["id"]] = (d, y, sk, det)

    def _score(c):
        return soft_score(job, c.get("resume_parsed", {}))

    soft_results = map_llm(candidates, _score, max_workers=3)

    w_d = weights.get("degree", 0.25)
    w_y = weights.get("years", 0.15)
    w_sk = weights.get("skills", 0.35)
    w_so = weights.get("soft", 0.25)
    hard_sum = w_d + w_y + w_sk

    for c, sr in zip(candidates, soft_results):
        d, y, sk, det = hard_map[c["id"]]
        if isinstance(sr, dict) and "error" in sr:
            soft_s = 0
            mp, gp, summ = [], [f"软性评分失败：{sr['error']}"], "软性评分未完成"
        else:
            soft_s = int(sr.get("soft_score", 0))
            mp = sr.get("matched_points", [])
            gp = sr.get("gap_points", [])
            summ = sr.get("summary", "")

        overall = round(d * w_d + y * w_y + sk * w_sk + soft_s * w_so)
        hard_s = round((d * w_d + y * w_y + sk * w_sk) / hard_sum) if hard_sum > 0 else 0

        deg_fail = (req_hard.get("degree") and d == 0)
        if hard_s < 50 or deg_fail:
            rec = "不推进"
        elif overall >= th_pass:
            rec = "推进"
        elif overall >= th_hold:
            rec = "待定"
        else:
            rec = "不推进"

        gap = list(gp)
        if det["missing"]:
            gap.append(f"硬性技能缺失：{', '.join(det['missing'])}")

        match_data = {
            "overall_score": overall,
            "hard_score": hard_s,
            "soft_score": soft_s,
            "recommendation": rec,
            "weights_used": {"degree": w_d, "years": w_y, "skills": w_sk, "soft": w_so},
            "breakdown": {
                "education_match": {"score": d, "reason": det["degree_reason"], "weight": w_d},
                "experience_match": {"score": y, "reason": det["years_reason"], "weight": w_y},
                "skills_match": {"score": sk, "reason": det["skills_reason"], "weight": w_sk},
                "project_relevance": {"score": soft_s, "reason": summ, "weight": w_so},
            },
            "matched_points": mp,
            "gap_points": gap,
            "summary": summ,
        }
        cand = load_candidate(c["id"])
        mj = cand.get("matched_jobs") or {}
        prev = mj.get(job_id, {}) or {}
        match_data["screen_decision"] = prev.get("screen_decision", "待审核")
        match_data["screen_note"] = prev.get("screen_note", "")
        mj[job_id] = match_data
        cand["matched_jobs"] = mj
        save_candidate(cand)

    return len(candidates)


# ────────────────────────────────────────────────────────────
# UI · 岗位选择器
# ────────────────────────────────────────────────────────────
def _render_job_selector() -> None:
    """两级下拉 + 选定按钮。选定后写 session_state["current_job_id"]。"""
    section("🎯 岗位范围", "先选岗位大类，再选具体岗位，按「选定」确认")

    # 当前已选中的岗位（若有）显示
    current_id = st.session_state.get("current_job_id")
    current_job = load_job(current_id) if current_id else None
    if current_job:
        st.markdown(
            f"<div style='color:{TOKENS['text-3']};font-size:.85rem;margin-bottom:4px'>"
            f"当前选中：<b style='color:{TOKENS['brand']}'>"
            f"{current_job['category']} · {current_job['title']}</b></div>",
            unsafe_allow_html=True,
        )

    c1, c2, c3 = st.columns([2, 3, 1])
    with c1:
        cat = st.selectbox(
            "岗位范围",
            options=JOB_CATEGORIES,
            index=(JOB_CATEGORIES.index(current_job["category"])
                   if current_job else 0),
            key="job_selector_cat",
        )
    with c2:
        if cat == "高风险复核池":
            st.selectbox(
                "具体岗位",
                options=["（即将上线）"],
                disabled=True,
                key="job_selector_specific_disabled",
            )
            picked_job = None
        else:
            jobs_in_cat = jobs_in_category(cat)
            if not jobs_in_cat:
                st.selectbox(
                    "具体岗位",
                    options=["（该类别下暂无岗位）"],
                    disabled=True,
                    key="job_selector_specific_empty",
                )
                picked_job = None
            else:
                labels = [f"{j['title']} · {j.get('dept', '')} · 招{j.get('count', 1)}人"
                          for j in jobs_in_cat]
                # 若当前选中的岗位在这个分类里，默认选它
                default_idx = 0
                if current_job and current_job["category"] == cat:
                    for i, j in enumerate(jobs_in_cat):
                        if j["id"] == current_job["id"]:
                            default_idx = i
                            break
                picked_label = st.selectbox(
                    "具体岗位",
                    options=labels,
                    index=default_idx,
                    key="job_selector_specific",
                )
                picked_job = jobs_in_cat[labels.index(picked_label)]
    with c3:
        st.markdown("<div style='padding-top:28px'></div>",
                    unsafe_allow_html=True)
        confirm = st.button(
            "✔ 选定", type="primary",
            key="confirm_job",
            use_container_width=True,
            disabled=(picked_job is None),
        )
        if confirm and picked_job:
            st.session_state["current_job_id"] = picked_job["id"]
            st.rerun()


# ────────────────────────────────────────────────────────────
# UI · 岗位详情（在同页展示）
# ────────────────────────────────────────────────────────────
def _render_job_header(job: dict) -> None:
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin:8px 0 4px'>"
        f"<span style='font-size:1.4rem;font-weight:660;color:{TOKENS['text']}'>"
        f"💼 {job['title']}</span>"
        f"<span class='pill brand'>{job.get('dept', '—')}</span>"
        f"<span style='color:{TOKENS['text-3']};font-size:.85rem'>"
        f"· {job.get('level', '')} · {job.get('location', '')} · "
        f"招 {job.get('count', 1)} 人</span>"
        f"</div>"
        f"<div style='color:{TOKENS['text-2']};font-size:.9rem;margin-bottom:6px'>"
        f"学历 <b>{job['hard'].get('degree', '—')}</b> · "
        f"年限 <b>≥{int(job['hard'].get('min_years', 0) or 0)}年</b> · "
        f"必备 <b>{('、'.join(job['hard'].get('must_skills', [])) or '—')}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_weights_and_thresholds(job: dict):
    """展示可交互权重/阈值滑块，返回 (weights_normalized, thresholds)。"""
    job_id = job["id"]
    default_w = job.get("recommended_weights") or {
        "degree": 0.25, "years": 0.15, "skills": 0.35, "soft": 0.25}
    default_th = job.get("recommended_thresholds") or {"pass": 80, "hold": 60}

    for d in _WEIGHT_DIMS:
        key = f"screen_w_{job_id}_{d}"
        if key not in st.session_state:
            st.session_state[key] = int(round(default_w.get(d, 0.25) * 100))
    for th, defv in [("pass", 80), ("hold", 60)]:
        key = f"screen_th_{th}_{job_id}"
        if key not in st.session_state:
            st.session_state[key] = int(default_th.get(th, defv))

    default_summary = " · ".join(
        f"{_DIM_LABEL[d]} {int(default_w.get(d, 0) * 100)}%" for d in _WEIGHT_DIMS)
    section("⚖️ 四维权重", f"岗位推荐：{default_summary}（HR 可覆盖）")
    for label, dim in [("学历", "degree"), ("年限", "years"),
                       ("必备技能", "skills"), ("软实力", "soft")]:
        cL, cR = st.columns([1, 5])
        cL.markdown(
            f"<div style='padding-top:12px;color:{TOKENS['text-2']};font-size:.9rem'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )
        with cR:
            st.slider(f"{label}权重 %", 0, 100, key=f"screen_w_{job_id}_{dim}",
                      label_visibility="collapsed")

    section("🎯 推荐 / 待定 / 不推进 分数线",
            f"岗位推荐：≥{default_th.get('pass', 80)} 推进 · ≥{default_th.get('hold', 60)} 待定")
    r5a, r5b = st.columns(2)
    with r5a:
        st.slider("推荐阈值", 50, 100, key=f"screen_th_pass_{job_id}")
    with r5b:
        st.slider("待定阈值", 30, 90, key=f"screen_th_hold_{job_id}")
    th_pass = st.session_state[f"screen_th_pass_{job_id}"]
    th_hold = st.session_state[f"screen_th_hold_{job_id}"]
    if th_pass <= th_hold:
        st.markdown(
            f"<div style='color:{TOKENS['danger']};font-size:.85rem'>"
            f"⚠ 推荐阈值需大于待定阈值，否则会失效</div>",
            unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='color:{TOKENS['text-2']};font-size:.85rem'>"
            f"当前分档：≥ <b>{th_pass}</b> 推进 · "
            f"[<b>{th_hold}</b>, {th_pass}) 待定 · &lt; {th_hold} 不推进"
            f"</div>",
            unsafe_allow_html=True)

    weights = _normalize_weights(
        {d: st.session_state[f"screen_w_{job_id}_{d}"] for d in _WEIGHT_DIMS})
    thresholds = {"pass": int(th_pass), "hold": int(th_hold)}
    return weights, thresholds


def _render_screening_trigger(job: dict, weights: dict, thresholds: dict) -> None:
    candidates = list_candidates()
    section("🚀 批量筛选",
            f"候选人库 {len(candidates)} 份 · 针对本岗位「{job['title']}」跑匹配评分")

    disabled = (not candidates) or (thresholds["pass"] <= thresholds["hold"])
    if not candidates:
        st.info("候选人库为空，请先把简历数据放入 sessions/candidates/")
    if st.button("🚀 开始筛选（硬性规则 + 软性 LLM）", type="primary",
                 key=f"run_screen_{job['id']}", disabled=disabled):
        with st.status("筛选中（硬性规则同步 + 软性并发 LLM）...", expanded=True) as s:
            n = run_screening(job, weights, thresholds)
            s.write(f"已完成 {n} 位候选人的匹配评分")
            s.update(label="筛选完成", state="complete")
        st.success(f"已为 {n} 位候选人生成对「{job['title']}」的匹配评价")
        st.rerun()


def _render_ranking_and_review(job: dict) -> None:
    job_id = job["id"]
    candidates = list_candidates()
    scored = [c for c in candidates if _get_match(c, job_id)]
    if not scored:
        return
    ranked = sorted(scored,
                    key=lambda c: _get_match(c, job_id)["overall_score"],
                    reverse=True)

    section("🏆 匹配排名与审核",
            f"卡片按对「{job['title']}」的总分排序；点选「通过 / 不通过」即完成审核")

    st.markdown(
        f"""<style>
        div[data-testid="stPopover"] > div > button,
        div[data-testid="stPopover"] button[kind="secondary"] {{
            background-color: {TOKENS['success']} !important;
            color: #ffffff !important;
            border-color: {TOKENS['success']} !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stPopover"] button:hover {{
            background-color: #047857 !important;
            border-color: #047857 !important;
            color: #ffffff !important;
        }}
        div[data-testid="stPopover"] button * {{
            color: #ffffff !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )

    _REC_PILL = {"推进": "success", "待定": "warning", "不推进": "danger"}
    _DECISION_OPTS = ["待审核", "通过筛选", "不通过"]
    for c in ranked:
        _render_candidate_card(c, job, _REC_PILL, _DECISION_OPTS)


def _render_candidate_card(c: dict, job: dict,
                           rec_pill_map: dict, decision_opts: list) -> None:
    job_id = job["id"]
    mr = _get_match(c, job_id)
    if not mr:
        return
    rec = mr.get("recommendation", "待定")
    rec_cls = rec_pill_map.get(rec, "neutral")
    total = mr["overall_score"]
    tone = score_tone(total)
    total_color = TOKENS.get(tone, TOKENS["brand"])
    grade_map = {"success": "优秀", "brand": "良好",
                 "warning": "待改进", "danger": "不推荐"}
    grade_text = grade_map.get(tone, "—")
    is_grey = (rec == "不推进")
    dim = "opacity:.55;" if is_grey else ""
    hard_s = mr["hard_score"]
    soft_s = mr["soft_score"]
    matched = mr.get("matched_points", []) or []
    gap = mr.get("gap_points", []) or []
    summ = mr.get("summary", "") or "—"

    with st.container(border=True):
        st.markdown(
            f"<div style='{dim}display:flex;align-items:center;gap:10px;"
            f"margin-bottom:12px'>"
            f"<span style='font-size:1.05rem;font-weight:640;color:{TOKENS['text']}'>"
            f"👤 {c.get('name', c['id'])}</span>"
            f"<span class='pill {rec_cls}'>{rec}</span>"
            f"<span style='color:{TOKENS['text-3']};font-size:.75rem'>"
            f"· 状态 {c.get('status', 'new')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        col_L, col_M, col_R, col_D = st.columns([1.1, 2, 2.2, 1])
        with col_L:
            st.markdown(
                f"<div style='{dim}background:{TOKENS['brand-50']};"
                f"border-radius:12px;padding:16px 12px;text-align:center'>"
                f"<div style='font-size:2.4rem;font-weight:720;"
                f"color:{total_color};line-height:1'>{total}</div>"
                f"<div style='color:{TOKENS['text-3']};font-size:.72rem;"
                f"margin-top:2px'>/100 综合得分</div>"
                f"<div style='margin-top:10px'>"
                f"<span class='pill {tone}'>{grade_text}</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_M:
            bars_html = (
                f"<div style='{dim}'>"
                "<div class='bar-row'>"
                f"<div class='br-label'>硬性分</div>"
                f"<div class='br-track'><div class='br-fill' "
                f"style='width:{hard_s}%;background:{TOKENS['brand']}'></div></div>"
                f"<div class='br-value' style='color:{TOKENS['brand']}'>{hard_s}</div>"
                "</div>"
                "<div class='bar-row'>"
                f"<div class='br-label'>软性分</div>"
                f"<div class='br-track'><div class='br-fill' "
                f"style='width:{soft_s}%;background:{TOKENS['success']}'></div></div>"
                f"<div class='br-value' style='color:{TOKENS['success']}'>{soft_s}</div>"
                "</div>"
                "</div>"
            )
            chips = []
            for p in matched[:3]:
                chips.append(
                    f"<span class='pill success' style='font-size:.7rem'>✅ {p}</span>")
            for g in gap[:2]:
                chips.append(
                    f"<span class='pill warning' style='font-size:.7rem'>⚠ {g}</span>")
            chips_html = ""
            if chips:
                chips_html = (
                    f"<div style='{dim}display:flex;flex-wrap:wrap;gap:6px;"
                    f"margin-top:8px'>" + "".join(chips) + "</div>"
                )
            st.markdown(bars_html + chips_html, unsafe_allow_html=True)
        with col_R:
            st.markdown(
                f"<div style='{dim}'>"
                f"<div style='background:{TOKENS['brand-50']};"
                f"border-left:3px solid {TOKENS['brand']};border-radius:8px;"
                f"padding:10px 14px;color:{TOKENS['text-2']};font-size:.85rem;"
                f"line-height:1.55'>{summ}</div>"
                f"<div style='color:{TOKENS['text-3']};font-size:.65rem;"
                f"text-align:right;margin-top:4px;letter-spacing:.04em'>"
                f"🤖 AI 匹配评价</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_D:
            with st.popover("👁 查看详情", use_container_width=True):
                _BD_LABEL = {"education_match": "学历",
                             "experience_match": "年限",
                             "skills_match": "必备技能",
                             "project_relevance": "软实力"}
                st.markdown(f"**{c.get('name', c['id'])} · {job['title']} 匹配详情**")
                for k, v in mr.get("breakdown", {}).items():
                    label = _BD_LABEL.get(k, k)
                    w_pct = int(round(v.get("weight", 0) * 100)) if "weight" in v else None
                    w_str = f"（权重 {w_pct}%）" if w_pct is not None else ""
                    st.markdown(f"- **{label}**{w_str}：{v['score']} 分 — {v['reason']}")
                if matched:
                    st.markdown("**全部匹配点**：" + "、".join(matched))
                if gap:
                    st.markdown("**全部差距点**：" + "、".join(gap))
            # TODO(面试模块对接)：把 disabled 去掉，改成 st.popover 或跳转到面试页
            st.button("🤖 面试例题 · 即将上线",
                      key=f"interview_placeholder_{c['id']}_{job_id}",
                      use_container_width=True, disabled=True)

        ac1, ac2, ac3 = st.columns([2, 3, 1])
        cur = mr.get("screen_decision", "待审核")
        if cur not in decision_opts:
            cur = "待审核"
        with ac1:
            decision = st.radio(
                "审核", decision_opts,
                index=decision_opts.index(cur),
                key=f"dec_{c['id']}_{job_id}",
                horizontal=True, label_visibility="collapsed",
            )
        with ac2:
            note = st.text_input(
                "备注", value=mr.get("screen_note", ""),
                key=f"note_{c['id']}_{job_id}",
                placeholder="推送给 HR 的备注（可留空）",
                label_visibility="collapsed",
            )
        with ac3:
            if st.button("提交", key=f"submit_{c['id']}_{job_id}",
                         use_container_width=True):
                cand = load_candidate(c["id"])
                mj = cand.get("matched_jobs") or {}
                sub = mj.get(job_id, {}) or {}
                sub["screen_decision"] = decision
                sub["screen_note"] = note
                mj[job_id] = sub
                cand["matched_jobs"] = mj
                if decision == "通过筛选":
                    cand["status"] = "screened"
                    tag = f"已通过筛选:{job_id}"
                    tags = cand.get("tags") or []
                    if tag not in tags:
                        tags = tags + [tag]
                    cand["tags"] = tags
                save_candidate(cand)
                if decision == "通过筛选":
                    st.success("已通过筛选，已推送 HR 电话初面")
                else:
                    st.info(f"已记录：{decision}")
                st.rerun()


# ────────────────────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────────────────────
def render():
    st.header("📋 简历筛选")
    st.caption("选定海信在招岗位 → AI 匹配评分 → 卡片式审核")

    _render_job_selector()

    job_id = st.session_state.get("current_job_id")
    job = load_job(job_id) if job_id else None
    if not job:
        st.info("请在上方选择一个具体岗位后按「选定」，页面下方将展示该岗位的匹配流程。")
        return

    st.divider()
    _render_job_header(job)
    with st.expander("📄 查看完整 JD 描述", expanded=False):
        st.markdown(job.get("jd_text", "（无 JD 描述）"))

    st.divider()
    weights, thresholds = _render_weights_and_thresholds(job)
    _render_screening_trigger(job, weights, thresholds)
    _render_ranking_and_review(job)
