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
from app.parser import parse_uploaded_file
from app.ui.theme import score_tone, TOKENS

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
SYSTEM_JD_TEXT = "你是资深 HR，把结构化任职要求扩写为一段专业、简洁、可直接发布的中文招聘 JD 文案，使用 Markdown 格式。"

# 四维权重字段（新契约）
_WEIGHT_DIMS = ["degree", "years", "skills", "soft"]
_DIM_LABEL = {"degree": "学历", "years": "年限", "skills": "必备技能", "soft": "软实力"}

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


def _normalize_weights(raw: dict) -> dict:
    """把四维权重（任意正数）归一化到和为 1。全零则退回均分。"""
    vals = {d: max(0.0, float(raw.get(d, 0) or 0)) for d in _WEIGHT_DIMS}
    total = sum(vals.values())
    if total <= 0:
        return {d: 1.0 / len(_WEIGHT_DIMS) for d in _WEIGHT_DIMS}
    return {d: v / total for d, v in vals.items()}


def _legacy_weights(jd: dict) -> bool:
    """检测旧 schema（hard/soft 二维权重）→ 需要用户重新保存。"""
    w = (jd or {}).get("weights", {}) or {}
    return "hard" in w and "degree" not in w


def _split_csv(s: str) -> list:
    """支持中/英文逗号分隔。"""
    return [x.strip() for x in (s or "").replace("，", ",").split(",") if x.strip()]


def _apply_form_seed():
    """把 pending 的表单种子写回 session_state（必须在 widget 创建之前调用）。"""
    seed = st.session_state.pop("_jd_form_seed", None)
    if seed:
        for k, v in seed.items():
            st.session_state[k] = v


def render_jd_section():
    """三步式：基本岗位信息 → AI 生成 JD → 确认筛选规则。生成的 JD 由 ② 展示。"""
    st.subheader("① 岗位任职要求")

    _apply_form_seed()

    jd = load_jd() or {}

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
    with r1a: st.text_input("岗位", key="jd_position",
                            placeholder="例：质量工程师")
    with r1b: st.text_input("所属部门", key="jd_dept",
                            placeholder="例：质量部")
    with r1c: st.number_input("招聘人数", min_value=1, step=1, key="jd_count")
    r2a, r2b, r2c = st.columns(3)
    with r2a: st.text_input("职级", key="jd_level",
                            placeholder="例：P5 / T3")
    with r2b: st.text_input("工作地点", key="jd_location",
                            placeholder="例：上海")
    with r2c: st.number_input("最低年限（年）", min_value=0, step=1, key="jd_years")
    st.text_input("学历要求", key="jd_degree",
                  placeholder="例：本科 / 硕士")
    st.text_area("基本任职要求（一句话概述岗位内容）", key="jd_base_req", height=68)

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

    r4a, r4b = st.columns(2)
    with r4a: st.text_input("必备技能（逗号分隔）", key="jd_must",
                            placeholder="例：ISO 9001, 8D, FMEA")
    with r4b: st.text_input("加分技能（逗号分隔，不参与权重）",
                            key="jd_nice", placeholder="例：六西格玛, APQP")
    st.text_input("软实力要求（逗号分隔）", key="jd_soft",
                  placeholder="例：沟通协作, 数据分析, 抗压能力")

    st.divider()

    st.caption("锁定评分标准，确保不同 HR 用同一把尺。")

    st.markdown("**四维权重**（前三项为硬性、最后一项为软性）")
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
    if total_pct == 100:
        st.markdown(
            f"<div style='color:{TOKENS['success']};font-size:.85rem'>"
            f"权重合计：{total_pct}% ✅</div>",
            unsafe_allow_html=True)
    elif total_pct == 0:
        st.markdown(
            f"<div style='color:{TOKENS['danger']};font-size:.85rem'>"
            f"权重合计：0% — 请至少给一个维度分配权重</div>",
            unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='color:{TOKENS['warning']};font-size:.85rem'>"
            f"权重合计：{total_pct}%（筛选时会自动归一化到 100%）</div>",
            unsafe_allow_html=True)

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
    if st.button("📝 生成 JD 描述并锁定筛选规则", type="primary",
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
                s.update(label="LLM 失败，占位文案已放入 ②", state="error")

        save_jd({
            "title": req["title"],
            "basics": basics,
            "requirements": req,
            "weights": weights,
            "thresholds": thresholds,
            "jd_text_generated": jd_text,
            "raw_text": st.session_state.get("jd_raw", ""),
        })
        st.success("已保存基本信息、筛选规则和 JD 描述；下方 ② 查看/编辑生成的 JD")
        st.rerun()


# ────────────────────────────────────────────────────────────
# 2. 简历库导入与解析
# ────────────────────────────────────────────────────────────
def render_jd_text_section():
    """② 展示 LLM 生成的最终 JD 描述，允许编辑保存。"""
    st.subheader("② 最终 JD 描述")
    jd = load_jd() or {}
    req = jd.get("requirements")
    jd_text = jd.get("jd_text_generated", "")

    if not req:
        st.info("请先在 ① 填写任职要求并点「生成 JD 描述并保存」。")
        return
    if not jd_text:
        st.info("已保存任职要求，但尚未生成 JD 描述。回到 ① 点「生成 JD 描述并保存」。")
        return

    # 顶部结构化摘要
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
    """从 mock 库批量导入 + 上传真实 PDF/Word/txt，解析后写入候选人文件。"""
    st.subheader("③ 简历库导入")
    st.caption("演示库用于快速跑通，上传区吃真实 PDF/Word；两者可同时勾选，一并解析。")

    files = sorted(f for f in os.listdir(RESUMES_DIR) if f.endswith(".txt"))
    options = {f: _infer_name(f) for f in files}
    if "demo_ms" not in st.session_state:
        st.session_state["demo_ms"] = []

    col_L, col_R = st.columns(2)
    with col_L:
        st.markdown("**演示简历库**")
        bc1, bc2, _ = st.columns([1, 1, 2])
        if bc1.button("全选", key="demo_all", use_container_width=True):
            st.session_state["demo_ms"] = list(options.keys())
            st.rerun()
        if bc2.button("清空", key="demo_none", use_container_width=True):
            st.session_state["demo_ms"] = []
            st.rerun()
        selected = st.multiselect(
            "选择演示简历",
            options=list(options.keys()),
            format_func=lambda f: options[f],
            key="demo_ms",
            label_visibility="collapsed",
        )
    with col_R:
        st.markdown("**上传真实简历**")
        st.caption("PDF / Word / txt，可多选；文件走内存解析，不落磁盘。")
        uploaded = st.file_uploader(
            "上传简历",
            type=["pdf", "docx", "doc", "txt", "md"],
            accept_multiple_files=True,
            key="upload_resumes",
            label_visibility="collapsed",
        )

    if st.button("📥 导入并解析选中简历", type="primary", key="import_resumes"):
        # 统一工作单元：(展示名, 原始字节, 文件名, 契约 resume_file 值)
        work = []
        for f in selected:
            with open(os.path.join(RESUMES_DIR, f), "rb") as fh:
                work.append((options[f], fh.read(), f,
                             os.path.join("mock", "resumes", f)))
        for u in (uploaded or []):
            work.append((_infer_name(u.name), u.getvalue(), u.name,
                         f"(上传) {u.name}"))

        if not work:
            st.warning("请至少选择或上传一份简历")
            return

        with st.status(f"解析 {len(work)} 份简历中...", expanded=True) as s:
            # 第 1 步：格式 → 纯文本（同步；文字型很快，失败单独记录不炸批次）
            s.write("① 提取简历文本（PDF/Word/txt）...")
            texts, failed = [], []
            for disp, raw, fname, rfile in work:
                try:
                    text = parse_uploaded_file(raw, fname)
                    texts.append((disp, text, rfile))
                except ValueError as e:
                    failed.append((fname, str(e)))
            if failed:
                s.write(f"⚠ {len(failed)} 份无法提取文本，已跳过")

            # 第 2 步：LLM 结构化（并发，复用现有 parse_resume，零改动）
            s.write(f"② LLM 结构化 {len(texts)} 份...")

            def _structure(item):
                disp, text, rfile = item
                parsed = parse_resume(text)
                name = parsed.get("name") or disp
                cid = "cand_" + re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", name)[:8]
                cand = {
                    "id": cid,
                    "name": name,
                    "resume_text": text,
                    "resume_file": rfile,
                    "resume_parsed": parsed,
                    "status": "new",
                    "tags": parsed.get("skills", []),
                }
                save_candidate(cand)
                return name

            results = map_llm(texts, _structure, max_workers=3)
            ok = [r for r in results
                  if not (isinstance(r, dict) and "error" in r)]
            s.write(f"成功导入 {len(ok)}/{len(work)} 份")
            s.update(label="简历库导入完成", state="complete")

        if ok:
            st.session_state["imported_this_session"] = True
            st.success(f"已导入 {len(ok)} 份简历到候选人库")
        if failed:
            with st.expander(f"⚠ {len(failed)} 份未能导入（点击看原因）"):
                for fname, reason in failed:
                    st.markdown(f"- **{fname}**：{reason}")
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
        st.warning("请先在 ① 填写任职要求，并点「生成 JD 描述并保存」")
        return
    if not candidates:
        st.warning("请先在 ③ 导入简历")
        return

    weights_raw = jd.get("weights", {}) or {}
    if _legacy_weights(jd):
        st.warning("此 JD 使用旧版权重结构，将按四维默认权重（学历25/年限15/技能35/软实力25）临时替代。请回到 ① 重新保存以固化。")
        weights = _normalize_weights({"degree": 25, "years": 15, "skills": 35, "soft": 25})
    else:
        weights = _normalize_weights(weights_raw)

    st.subheader("④ 批量筛选")
    imported = st.session_state.get("imported_this_session", False)
    if not imported:
        st.info("请先在 ③ 导入至少一份简历，再开始筛选")
    if st.button("🚀 开始筛选（硬性规则 + 软性 LLM）", type="primary",
                 key="run_screen", disabled=not imported):
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
    st.header("简历筛选（AI 智能甄选）")
    render_jd_section()
    st.divider()
    render_jd_text_section()
    st.divider()
    render_resume_library()
    st.divider()
    render_screening()
