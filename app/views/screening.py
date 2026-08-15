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
from app.shared.job_utils import (
    _WEIGHT_DIMS,
    _DIM_LABEL,
    _DEGREE_LEVEL,
    _normalize_weights,
    _split_csv,
    _legacy_weights,
)
from app.parser import parse_uploaded_file
from app.ui.theme import score_tone, TOKENS

# 简历库目录（A 提供的 mock 数据，已提交 git）
RESUMES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mock", "resumes",
)

SYSTEM_PARSE = "你是简历解析专家，提取简历关键信息为结构化 JSON。只输出 JSON。"
SYSTEM_SOFT = "你是资深技术招聘专家，评估候选人与岗位的软性素质匹配。只输出 JSON。"


# ────────────────────────────────────────────────────────────
# 1. 简历库导入与解析（演示数据自动加载，无人工选择界面）
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
def run_screening(jd: dict, weights: dict, thresholds: dict = None):
    """对全部候选人执行硬性规则 + 软性 LLM 评分，写回 match_result。
    weights 为四维归一化字典 {degree, years, skills, soft}；
    thresholds 为 {"pass": int, "hold": int} 分数线，默认 80/60。"""
    thresholds = thresholds or {"pass": 80, "hold": 60}
    th_pass = int(thresholds.get("pass", 80))
    th_hold = int(thresholds.get("hold", 60))
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
    w_d = weights.get("degree", 0.25)
    w_y = weights.get("years", 0.15)
    w_sk = weights.get("skills", 0.35)
    w_so = weights.get("soft", 0.25)
    hard_sum = w_d + w_y + w_sk  # 用于「硬性总括分」加权平均展示

    for c, sr in zip(candidates, soft_results):
        d, y, sk, det = hard_map[c["id"]]
        if isinstance(sr, dict) and "error" in sr:
            soft_s, mp, gp, summ = 0, [], [f"软性评分失败：{sr['error']}"], "软性评分未完成"
        else:
            soft_s = int(sr.get("soft_score", 0))
            mp = sr.get("matched_points", [])
            gp = sr.get("gap_points", [])
            summ = sr.get("summary", "")

        # 四维加权总分
        overall = round(d * w_d + y * w_y + sk * w_sk + soft_s * w_so)
        # 硬性总括分（三项按权重加权平均，为候选人卡片的「硬性分」总括条服务）
        hard_s = round((d * w_d + y * w_y + sk * w_sk) / hard_sum) if hard_sum > 0 else 0

        # 一票否决：学历门槛不满足 或 硬性总括太低（50 为默认硬性底线）
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

        match_result = {
            "overall_score": overall,
            "hard_score": hard_s,
            "soft_score": soft_s,
            "recommendation": rec,
            "weights_used": {"degree": w_d, "years": w_y,
                             "skills": w_sk, "soft": w_so},
            "breakdown": {
                "education_match": {"score": d, "reason": det["degree_reason"],
                                    "weight": w_d},
                "experience_match": {"score": y, "reason": det["years_reason"],
                                     "weight": w_y},
                "skills_match": {"score": sk, "reason": det["skills_reason"],
                                 "weight": w_sk},
                "project_relevance": {"score": soft_s, "reason": summ,
                                      "weight": w_so},
            },
            "matched_points": mp,
            "gap_points": gap,
            "summary": summ,
        }
        update_candidate(c["id"], "match_result", match_result)

    cache = {c["id"]: c.get("match_result") for c in list_candidates()
             if c.get("match_result")}
    save_demo_cache("screening_batch", cache)
    return len(candidates)


def render_screening():
    """触发批量筛选 + 排名表 + 用人部门审核。"""
    jd = load_jd()
    candidates = list_candidates()
    if not jd or not jd.get("requirements"):
        st.warning("请先在「岗位投放」页填写任职要求并生成 JD 描述，再回到本页筛选。")
        return
    if not candidates:
        st.warning("候选人库为空。请先准备简历数据（演示环境可放置到 sessions/candidates/ 或 mock/resumes/）。")
        return

    weights_raw = jd.get("weights", {}) or {}
    if _legacy_weights(jd):
        st.warning("此 JD 使用旧版权重结构，将按四维默认权重（学历25/年限15/技能35/软实力25）临时替代。请回到「岗位投放」页重新保存以固化。")
        weights = _normalize_weights({"degree": 25, "years": 15, "skills": 35, "soft": 25})
    else:
        weights = _normalize_weights(weights_raw)

    st.subheader("批量筛选")
    st.caption(f"候选人库已加载 {len(candidates)} 份简历；点击下方按钮开始匹配评分。")
    if st.button("🚀 开始筛选（硬性规则 + 软性 LLM）", type="primary",
                 key="run_screen", disabled=not candidates):
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
                n = run_screening(jd, weights, jd.get("thresholds"))
                s.write(f"已完成 {n} 位候选人的匹配评分")
                s.update(label="筛选完成", state="complete")
            st.success(f"已为 {n} 位候选人生成匹配评价")
        st.session_state["screening_ran"] = True
        st.rerun()

    # 排名表（仅在本次会话点过「开始筛选」后显示，避免历史 match_result 一进页面就冒出来）
    if not st.session_state.get("screening_ran"):
        return
    ranked = sorted(
        [c for c in candidates if c.get("match_result")],
        key=lambda c: c["match_result"]["overall_score"], reverse=True)
    if not ranked:
        return

    st.subheader("⑤ 匹配排名与审核")
    st.caption("卡片按总分排序；直接在卡片内点选「通过 / 不通过」即完成审核，通过者推送 HR 电话初面。")

    _REC_PILL = {"推进": "success", "待定": "warning", "不推进": "danger"}
    _DECISION_OPTS = ["待审核", "通过筛选", "不通过"]

    for c in ranked:
        _render_candidate_card(c, _REC_PILL, _DECISION_OPTS)


def _render_candidate_card(c: dict, rec_pill_map: dict, decision_opts: list):
    """一张候选人卡片：仿参考稿"综合评分"三栏卡片布局。"""
    mr = c["match_result"]
    rec = mr.get("recommendation", "待定")
    rec_cls = rec_pill_map.get(rec, "neutral")
    total = mr["overall_score"]
    tone = score_tone(total)  # success / brand / warning / danger
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
        # 头部：姓名 + 推荐 pill + 状态
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

        # 三栏：大数字 | 分数条+chip | AI 评价
        col_L, col_M, col_R = st.columns([1.1, 2, 2.4])
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
                f"<div style='color:{TOKENS['text-3']};font-size:.72rem;"
                f"margin-bottom:6px;letter-spacing:.04em'>🤖 AI 匹配评价</div>"
                f"<div style='background:{TOKENS['brand-50']};"
                f"border-left:3px solid {TOKENS['brand']};border-radius:8px;"
                f"padding:10px 14px;color:{TOKENS['text-2']};font-size:.85rem;"
                f"line-height:1.6'>{summ}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with st.expander("查看四维明细 / 全部匹配点 / 全部差距点", expanded=False):
            _BD_LABEL = {"education_match": "学历", "experience_match": "年限",
                         "skills_match": "必备技能", "project_relevance": "软实力"}
            for k, v in mr.get("breakdown", {}).items():
                label = _BD_LABEL.get(k, k)
                w_pct = int(round(v.get("weight", 0) * 100)) if "weight" in v else None
                w_str = f"（权重 {w_pct}%）" if w_pct is not None else ""
                st.markdown(f"- **{label}**{w_str}：{v['score']} 分 — {v['reason']}")
            if matched:
                st.markdown("**全部匹配点**：" + "、".join(matched))
            if gap:
                st.markdown("**全部差距点**：" + "、".join(gap))

        ac1, ac2, ac3 = st.columns([2, 3, 1])
        with ac1:
            cur = c.get("screen_decision", "待审核")
            if cur not in decision_opts:
                cur = "待审核"
            decision = st.radio(
                "审核",
                decision_opts,
                index=decision_opts.index(cur),
                key=f"dec_{c['id']}",
                horizontal=True,
                label_visibility="collapsed",
            )
        with ac2:
            note = st.text_input(
                "备注",
                value=c.get("screen_note", ""),
                key=f"note_{c['id']}",
                placeholder="推送给 HR 的备注（可留空）",
                label_visibility="collapsed",
            )
        with ac3:
            if st.button("提交", key=f"submit_{c['id']}", use_container_width=True):
                upd = {"screen_decision": decision, "screen_note": note}
                if decision == "通过筛选":
                    upd["status"] = "screened"
                    upd["tags"] = c.get("tags", []) + ["已通过筛选"]
                cand = load_candidate(c["id"])
                cand.update(upd)
                save_candidate(cand)
                if decision == "通过筛选":
                    st.success("已通过筛选，已推送 HR 电话初面")
                else:
                    st.info(f"已记录：{decision}")
                st.rerun()


# ────────────────────────────────────────────────────────────
# 页面入口
# ────────────────────────────────────────────────────────────
def render():
    st.header("简历筛选")
    render_screening()
