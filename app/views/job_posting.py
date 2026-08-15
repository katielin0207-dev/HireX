"""岗位投放模块（MVP 新增页面，由 A 维护）。

负责：岗位任职要求的录入 / AI 拆解已有 JD / 四维权重与分数线设置 /
       生成最终 JD 描述。生成的 JD 与筛选规则通过 app.shared.store 持久化，
       供简历筛选页读取使用。
"""
import streamlit as st

from app.shared import call_llm, save_jd, load_jd
from app.shared.job_utils import (
    _WEIGHT_DIMS,
    _DIM_LABEL,
    _normalize_weights,
    _split_csv,
    _legacy_weights,
)
from app.ui.theme import TOKENS

SYSTEM_JD = "你是资深 HR 招聘专家，善于把岗位描述拆解为结构化任职要求。只输出 JSON。"
SYSTEM_JD_TEXT = "你是资深 HR，把结构化任职要求扩写为一段专业、简洁、可直接发布的中文招聘 JD 文案，使用 Markdown 格式。"

# Demo 模拟数据（正式环境从北森读取；比赛 Demo 用这份）
_MOCK_BASICS = {
    "jd_position": "质量工程师",
    "jd_dept": "质量部",
    "jd_count": 2,
    "jd_level": "P5",
    "jd_location": "上海",
    "jd_base_req": "负责产品质量管控，参与供应商审核与不良品 8D 分析。",
    "jd_degree": "本科",
    "jd_years": 3,
    "jd_must": "ISO 9001, 8D, FMEA, SPC",
    "jd_nice": "六西格玛绿带, APQP",
    "jd_soft": "沟通协作, 数据分析, 抗压能力",
}


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


def generate_jd_text(structured: dict, weights: dict, basics: dict = None) -> str:
    """结构化任职要求 + 基本岗位信息 → 一段自然语言中文招聘 JD 文案。
    严格输出五段：岗位职责 / 学历经验 / 必备技能 / 加分技能 / 软实力。"""
    basics = basics or {}
    title = basics.get("position") or structured.get("title", "岗位")
    h = structured.get("hard", {})
    soft = structured.get("soft", [])
    w_bits = " · ".join(
        f"{_DIM_LABEL[d]} {int(weights.get(d, 0) * 100)}%" for d in _WEIGHT_DIMS)
    dept = basics.get("dept", "")
    count = basics.get("count", "")
    level = basics.get("level", "")
    location = basics.get("location", "")
    base_req = basics.get("base_requirements", "")

    prompt = f"""请根据以下岗位信息，生成一段专业、简洁、可直接发布到招聘平台的中文 JD 文案。

【基本信息】
- 岗位：{title}
- 所属部门：{dept or '—'}
- 招聘人数：{count or '—'}
- 职级：{level or '—'}
- 工作地点：{location or '—'}
- 基本任职要求：{base_req or '—'}

【结构化要求】
- 学历要求：{h.get('degree') or '不限'}
- 最低年限：{int(h.get('min_years', 0) or 0)} 年
- 必备技能：{'、'.join(h.get('must_skills', []) or ['—'])}
- 加分技能：{'、'.join(h.get('nice_skills', []) or ['无'])}
- 软实力要求：{'、'.join(soft or ['—'])}
- 筛选权重：{w_bits}

严格按以下 Markdown 五段结构输出（不要多加/少加段落，不要额外解释）：

# {{岗位名称}}

## 岗位职责
- 3-5 条主要职责，紧扣基本任职要求

## 学历与经验要求
- 学历、工作年限、行业背景等硬性要求

## 必备技能
- 具体技术/工具/方法论清单

## 加分技能
- 加分项，若无写「无」

## 软实力要求
- 沟通、协作、学习、抗压等
"""
    return call_llm(prompt, system=SYSTEM_JD_TEXT, expect_json=False)


def _apply_form_seed():
    """把 pending 的表单种子写回 session_state（必须在 widget 创建之前调用）。"""
    seed = st.session_state.pop("_jd_form_seed", None)
    if seed:
        for k, v in seed.items():
            st.session_state[k] = v


def render():
    """岗位投放页主渲染：任职信息 → 已有 JD 拆解 → 权重分数线 → 生成 JD。"""
    st.header("岗位投放")
    st.subheader("岗位任职要求")

    _apply_form_seed()

    jd = load_jd() or {}
    if _legacy_weights(jd):
        st.info("检测到旧版二维权重，请重新保存后进入简历筛选。")

    basics0 = jd.get("basics", {}) or {}
    req0 = jd.get("requirements", {}) or {}
    h0 = req0.get("hard", {})
    w0 = jd.get("weights", {}) or {}
    th0 = jd.get("thresholds", {}) or {}

    def _init(key, val):
        if key not in st.session_state:
            st.session_state[key] = val

    _init("jd_position", basics0.get("position") or jd.get("title") or req0.get("title", ""))
    _init("jd_dept", basics0.get("dept", ""))
    _init("jd_count", int(basics0.get("count", 1) or 1))
    _init("jd_level", basics0.get("level", ""))
    _init("jd_location", basics0.get("location", ""))
    _init("jd_base_req", basics0.get("base_requirements", ""))
    _init("jd_degree", h0.get("degree", "本科"))
    _init("jd_years", int(h0.get("min_years", 3) or 3))
    _init("jd_must", "，".join(h0.get("must_skills", [])))
    _init("jd_nice", "，".join(h0.get("nice_skills", [])))
    _init("jd_soft", "，".join(req0.get("soft", [])))
    _init("jd_raw", jd.get("raw_text", ""))
    default_pct = {"degree": 25, "years": 15, "skills": 35, "soft": 25}
    for d in _WEIGHT_DIMS:
        _init(f"jd_w_{d}", int(round(w0.get(d, default_pct[d] / 100) * 100)))
    _init("jd_th_pass", int(th0.get("pass", 80)))
    _init("jd_th_hold", int(th0.get("hold", 60)))

    r1a, r1b, r1c = st.columns(3)
    with r1a:
        st.text_input("岗位", key="jd_position", placeholder="例：质量工程师")
    with r1b:
        st.text_input("所属部门", key="jd_dept", placeholder="例：质量部")
    with r1c:
        st.number_input("招聘人数", min_value=1, step=1, key="jd_count")
    r2a, r2b, r2c = st.columns(3)
    with r2a:
        st.text_input("职级", key="jd_level", placeholder="例：P5 / T3")
    with r2b:
        st.text_input("工作地点", key="jd_location", placeholder="例：上海")
    with r2c:
        st.number_input("最低年限（年）", min_value=0, step=1, key="jd_years")
    st.text_input("学历要求", key="jd_degree", placeholder="例：本科 / 硕士")
    st.text_area("基本任职要求（一句话概述岗位内容）", key="jd_base_req", height=68)

    st.divider()

    r4a, r4b = st.columns(2)
    with r4a:
        st.text_input("必备技能（逗号分隔）", key="jd_must",
                      placeholder="例：ISO 9001, 8D, FMEA")
    with r4b:
        st.text_input("加分技能（逗号分隔，不参与权重）",
                      key="jd_nice", placeholder="例：六西格玛, APQP")
    st.text_input("软实力要求（逗号分隔）", key="jd_soft",
                  placeholder="例：沟通协作, 数据分析, 抗压能力")

    with st.expander("▼ 已有 JD？粘贴一键拆解自动填充", expanded=False):
        st.text_area(
            "岗位 JD 原文", key="jd_raw", height=140,
            placeholder="例如：招聘 Python 后端开发工程师，3年以上经验...",
        )
        if st.button("🔧 拆解填入表单", key="gen_jd_parse"):
            if not st.session_state["jd_raw"].strip():
                st.warning("请先粘贴 JD 原文")
            else:
                with st.status("解析 JD 中...", expanded=True) as s:
                    s.write("调用 LLM 拆解任职要求...")
                    try:
                        r = parse_jd(st.session_state["jd_raw"])
                    except Exception as e:
                        s.update(label=f"解析失败：{e}", state="error")
                        r = None
                    if r:
                        hd = r.get("hard", {})
                        st.session_state["_jd_form_seed"] = {
                            "jd_position": r.get("title", ""),
                            "jd_degree": hd.get("degree", "本科"),
                            "jd_years": int(hd.get("min_years", 0) or 0),
                            "jd_must": "，".join(hd.get("must_skills", [])),
                            "jd_nice": "，".join(hd.get("nice_skills", [])),
                            "jd_soft": "，".join(r.get("soft", [])),
                        }
                        s.update(label="已拆解，表单已自动填充", state="complete")
                        st.rerun()

    st.divider()

    st.markdown("**四维权重**")
    for label, dim in [("学历", "degree"), ("年限", "years"),
                       ("必备技能", "skills"), ("软实力", "soft")]:
        cL, cR = st.columns([1, 5])
        cL.markdown(
            f"<div style='padding-top:12px;color:{TOKENS['text-2']};font-size:.9rem'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )
        with cR:
            st.slider(f"{label}权重 %", 0, 100, key=f"jd_w_{dim}",
                      label_visibility="collapsed")

    total_pct = sum(st.session_state.get(f"jd_w_{d}", 0) for d in _WEIGHT_DIMS)

    st.markdown("**推荐 / 待定 / 不推进 分数线**")
    r5a, r5b = st.columns(2)
    with r5a:
        st.slider("推荐阈值（总分 ≥ 此值 → 推进）", 50, 100, key="jd_th_pass")
    with r5b:
        st.slider("待定阈值（总分 ≥ 此值 → 待定；低于则不推进）",
                  30, 90, key="jd_th_hold")
    th_pass = st.session_state["jd_th_pass"]
    th_hold = st.session_state["jd_th_hold"]
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

    st.markdown("")
    disabled = (total_pct == 0) or (th_pass <= th_hold)
    if st.button("📝 生成JD描述", type="primary",
                 key="gen_jd_final", disabled=disabled):
        basics = {
            "position": st.session_state["jd_position"].strip(),
            "dept": st.session_state["jd_dept"].strip(),
            "count": int(st.session_state["jd_count"]),
            "level": st.session_state["jd_level"].strip(),
            "location": st.session_state["jd_location"].strip(),
            "base_requirements": st.session_state["jd_base_req"].strip(),
        }
        req = {
            "title": basics["position"] or "岗位",
            "hard": {
                "degree": st.session_state["jd_degree"].strip(),
                "min_years": int(st.session_state["jd_years"]),
                "must_skills": _split_csv(st.session_state["jd_must"]),
                "nice_skills": _split_csv(st.session_state["jd_nice"]),
            },
            "soft": _split_csv(st.session_state["jd_soft"]),
        }
        weights = _normalize_weights(
            {d: st.session_state[f"jd_w_{d}"] for d in _WEIGHT_DIMS})
        thresholds = {"pass": int(th_pass), "hold": int(th_hold)}

        with st.status("生成 JD 描述中...", expanded=True) as s:
            s.write("调用 LLM 把结构化要求扩写为五段招聘文案...")
            try:
                jd_text = generate_jd_text(req, weights, basics)
                s.update(label="JD 描述已生成", state="complete")
            except Exception as e:
                jd_text = f"> ⚠ LLM 生成失败：{e}\n>\n> 请手动补写 JD 文案。"
                s.update(label="LLM 生成失败", state="error")

        save_jd({
            "title": req["title"],
            "basics": basics,
            "requirements": req,
            "weights": weights,
            "thresholds": thresholds,
            "jd_text_generated": jd_text,
            "raw_text": st.session_state.get("jd_raw", ""),
        })
        st.success("已生成 JD 描述，可在下方查看并编辑")
        st.rerun()

    # 生成后直接在按钮下方展示最终 JD 描述，可编辑保存
    jd = load_jd() or {}
    jd_text = jd.get("jd_text_generated", "")
    if jd_text:
        req = jd.get("requirements", {})
        h = req.get("hard", {})
        w = jd.get("weights", {}) or {}
        basics = jd.get("basics", {}) or {}
        th = jd.get("thresholds", {}) or {}
        must_preview = "、".join(h.get("must_skills", [])[:3]) or "—"
        line1 = " · ".join(x for x in [
            f"**{basics.get('position') or req.get('title', '岗位')}**",
            basics.get("dept") or None,
            (f"招聘 {basics.get('count')} 人" if basics.get("count") else None),
            basics.get("level") or None,
            basics.get("location") or None,
        ] if x)
        line2 = " · ".join([
            f"学历 {h.get('degree', '—')}",
            f"≥{int(h.get('min_years', 0) or 0)} 年",
            f"必备：{must_preview}",
        ])
        line3 = "权重 " + " / ".join(
            f"{_DIM_LABEL[d]} {int(w.get(d, 0) * 100)}%" for d in _WEIGHT_DIMS)
        if th:
            line3 += f" · 分档 ≥{th.get('pass', 80)} 推进 / ≥{th.get('hold', 60)} 待定"
        st.caption(line1)
        st.caption(line2 + " · " + line3)

        edited = st.text_area(
            "招聘文案（Markdown，可编辑）",
            value=jd_text,
            height=320,
            key="jd_text_edit",
        )
        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("💾 保存 JD", key="save_jd_text"):
                jd["jd_text_generated"] = edited
                save_jd(jd)
                st.success("已保存")
                st.rerun()
        with c2:
            with st.expander("预览渲染效果", expanded=False):
                st.markdown(edited)
