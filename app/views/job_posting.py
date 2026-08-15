"""岗位投放模块（MVP 新增页面，由 A 维护）。

负责：岗位任职要求的录入 / AI 拆解已有 JD / 生成最终 JD 描述。
       生成的 JD 与筛选规则通过 app.shared.store 持久化，供简历筛选页读取使用。
"""
import re

import streamlit as st

from app.config import settings
from app.shared import call_llm, save_jd, load_jd
from app.shared.demo_cache import demo_mode_enabled
from app.shared.job_utils import (
    _split_csv,
    _legacy_weights,
)
from app.shared.jobs import JOB_CATEGORIES, load_jobs
from app.ui import page_header, section
from app.ui.theme import TOKENS

SYSTEM_JD = "你是资深 HR 招聘专家，善于把岗位描述拆解为结构化任职要求。只输出 JSON。"
SYSTEM_JD_TEXT = "你是资深 HR，把结构化任职要求扩写为一段专业、简洁、可直接发布的中文招聘 JD 文案，使用 Markdown 格式。"
SYSTEM_JOB_PROFILE = (
    "你是海信容声家电制造企业的资深招聘专家。根据岗位模板完善岗位画像，"
    "不得虚构企业制度、薪资或无法验证的资质要求，只输出合法 JSON。"
)

def _responsibilities_from_jd(jd_text: str) -> list[str]:
    """从模板 JD 的岗位职责段提取要点。"""
    match = re.search(r"##\s*岗位职责\s*\n([\s\S]*?)(?=\n##|\Z)", jd_text or "")
    if not match:
        return []
    return [line.lstrip("- ").strip() for line in match.group(1).splitlines()
            if line.strip().startswith("-")]


def _template_job_profile(job: dict) -> dict:
    """岗位模板转成岗位创建页使用的统一画像结构。"""
    hard = job.get("hard") or {}
    responsibilities = _responsibilities_from_jd(job.get("jd_text", ""))
    base_requirements = "；".join(responsibilities[:2]) or f"负责{job.get('title', '岗位')}相关工作与结果交付。"
    return {
        "title": job.get("title", ""),
        "dept": job.get("dept", ""),
        "location": job.get("location", ""),
        "level": job.get("level", ""),
        "count": int(job.get("count", 1) or 1),
        "base_requirements": base_requirements,
        "hard": {
            "degree": hard.get("degree", "本科"),
            "min_years": int(hard.get("min_years", 0) or 0),
            "must_skills": list(hard.get("must_skills") or []),
            "nice_skills": list(hard.get("nice_skills") or []),
        },
        "soft": list(job.get("soft") or []),
        "responsibilities": responsibilities,
        "role_summary": f"{job.get('category', '招聘岗位')} · {job.get('title', '')}",
    }


def generate_job_profile(job: dict) -> tuple[dict, bool]:
    """基于岗位模板生成可编辑的初步岗位画像；返回 (画像, 是否使用AI)。"""
    fallback = _template_job_profile(job)
    if demo_mode_enabled() or not settings.is_configured:
        return fallback, False

    hard = job.get("hard") or {}
    prompt = f"""请完善以下企业招聘岗位的初步岗位画像。

【岗位模板】
- 岗位：{job.get('title', '')}
- 岗位类别：{job.get('category', '')}
- 部门：{job.get('dept', '')}
- 地点：{job.get('location', '')}
- 职级：{job.get('level', '')}
- 学历：{hard.get('degree', '不限')}
- 年限：{hard.get('min_years', 0)} 年
- 必备技能：{'、'.join(hard.get('must_skills', []))}
- 加分技能：{'、'.join(hard.get('nice_skills', []))}
- 软实力：{'、'.join(job.get('soft', []))}
- 现有JD：{(job.get('jd_text') or '')[:1600]}

输出 JSON：
{{
  "title": "岗位名称",
  "dept": "所属部门",
  "location": "工作地点",
  "level": "职级",
  "count": 招聘人数数字,
  "base_requirements": "一段80字以内的岗位目标与核心工作概述",
  "hard": {{
    "degree": "学历要求",
    "min_years": 最低年限数字,
    "must_skills": ["4-6项可核验的必备技能"],
    "nice_skills": ["2-4项加分技能"]
  }},
  "soft": ["3-5项与岗位场景相关的软实力"],
  "responsibilities": ["3-5条具体岗位职责"],
  "role_summary": "一句话岗位画像"
}}"""
    try:
        result = call_llm(prompt, system=SYSTEM_JOB_PROFILE, expect_json=True)
        if not isinstance(result, dict):
            return fallback, False
        result_hard = result.get("hard") if isinstance(result.get("hard"), dict) else {}
        profile = {
            **fallback,
            "title": str(result.get("title") or fallback["title"]),
            "dept": str(result.get("dept") or fallback["dept"]),
            "location": str(result.get("location") or fallback["location"]),
            "level": str(result.get("level") or fallback["level"]),
            "count": int(result.get("count") or fallback["count"]),
            "base_requirements": str(result.get("base_requirements") or fallback["base_requirements"])[:240],
            "hard": {
                "degree": str(result_hard.get("degree") or fallback["hard"]["degree"]),
                "min_years": int(result_hard.get("min_years") or fallback["hard"]["min_years"]),
                "must_skills": [str(x) for x in (result_hard.get("must_skills") or fallback["hard"]["must_skills"])][:8],
                "nice_skills": [str(x) for x in (result_hard.get("nice_skills") or fallback["hard"]["nice_skills"])][:6],
            },
            "soft": [str(x) for x in (result.get("soft") or fallback["soft"])][:6],
            "responsibilities": [str(x) for x in (result.get("responsibilities") or fallback["responsibilities"])][:6],
            "role_summary": str(result.get("role_summary") or fallback["role_summary"])[:120],
        }
        return profile, True
    except Exception:
        return fallback, False


def _profile_payload(profile: dict) -> tuple[dict, dict]:
    """岗位画像转换为现有 JD 数据契约。"""
    hard = profile.get("hard") or {}
    basics = {
        "position": profile.get("title", ""),
        "dept": profile.get("dept", ""),
        "count": int(profile.get("count", 1) or 1),
        "level": profile.get("level", ""),
        "location": profile.get("location", ""),
        "base_requirements": profile.get("base_requirements", ""),
    }
    requirements = {
        "title": profile.get("title", "") or "岗位",
        "hard": {
            "degree": hard.get("degree", "本科"),
            "min_years": int(hard.get("min_years", 0) or 0),
            "must_skills": list(hard.get("must_skills") or []),
            "nice_skills": list(hard.get("nice_skills") or []),
        },
        "soft": list(profile.get("soft") or []),
    }
    return basics, requirements


def _profile_form_seed(profile: dict) -> dict:
    hard = profile.get("hard") or {}
    return {
        "jd_position": profile.get("title", ""),
        "jd_dept": profile.get("dept", ""),
        "jd_count": int(profile.get("count", 1) or 1),
        "jd_level": profile.get("level", ""),
        "jd_location": profile.get("location", ""),
        "jd_base_req": profile.get("base_requirements", ""),
        "jd_degree": hard.get("degree", "本科"),
        "jd_years": int(hard.get("min_years", 0) or 0),
        "jd_must": "，".join(hard.get("must_skills") or []),
        "jd_nice": "，".join(hard.get("nice_skills") or []),
        "jd_soft": "，".join(profile.get("soft") or []),
    }


def _local_parse_jd(raw_text: str) -> dict:
    """无模型时用可解释规则提取常见 JD 字段。"""
    text = raw_text.strip()
    degree = next((d for d in ("博士", "硕士", "本科", "大专") if d in text), "不限")
    year_match = re.search(r"(\d+)\s*年(?:以上|及以上|经验)", text)
    min_years = int(year_match.group(1)) if year_match else 0
    known_skills = (
        "ISO 9001", "8D", "FMEA", "SPC", "APQP", "六西格玛", "Python",
        "Java", "SQL", "Excel", "供应商质量", "质量体系", "数据分析",
    )
    must = [skill for skill in known_skills if skill.lower() in text.lower()]
    soft_words = ("沟通协作", "跨部门沟通", "问题分析", "抗压能力", "团队协作", "学习能力")
    soft = [word for word in soft_words if word in text]
    title_match = re.search(r"(?:招聘|岗位[:：]?|职位[:：]?)\s*([^，。\n]{2,20})", text)
    title = title_match.group(1).strip() if title_match else "待确认岗位"
    return {
        "title": title,
        "hard": {
            "degree": degree,
            "min_years": min_years,
            "must_skills": must,
            "nice_skills": [],
        },
        "soft": soft,
    }


def _local_jd_text(structured: dict, basics: dict = None) -> str:
    """根据已确认字段生成稳定、可编辑的五段 JD。"""
    basics = basics or {}
    hard = structured.get("hard", {}) or {}
    soft = structured.get("soft", []) or []
    title = basics.get("position") or structured.get("title") or "招聘岗位"
    base_req = basics.get("base_requirements") or "负责岗位相关业务推进与结果交付。"
    must = hard.get("must_skills", []) or []
    nice = hard.get("nice_skills", []) or []
    return f"""# {title}

## 岗位职责
- {base_req}
- 协同相关部门推进重点任务，跟踪问题闭环并沉淀工作方法。
- 按业务目标完成数据分析、过程复盘与结果汇报。

## 学历与经验要求
- {hard.get('degree') or '学历不限'}，{int(hard.get('min_years', 0) or 0)} 年及以上相关工作经验。
- 有相关行业或同类岗位项目经验者优先。

## 必备技能
{chr(10).join(f'- {item}' for item in must) if must else '- 具备岗位所需的基础专业能力。'}

## 加分技能
{chr(10).join(f'- {item}' for item in nice) if nice else '- 无。'}

## 软实力要求
{chr(10).join(f'- {item}' for item in soft) if soft else '- 具备良好的沟通协作、学习与问题解决能力。'}"""


def parse_jd(raw_text: str) -> dict:
    """把 JD 原文解析为结构化任职要求。"""
    if demo_mode_enabled() or not settings.is_configured:
        return _local_parse_jd(raw_text)
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


def generate_jd_text(structured: dict, basics: dict = None) -> str:
    """结构化任职要求 + 基本岗位信息 → 一段自然语言中文招聘 JD 文案。
    严格输出五段：岗位职责 / 学历经验 / 必备技能 / 加分技能 / 软实力。"""
    basics = basics or {}
    if demo_mode_enabled() or not settings.is_configured:
        return _local_jd_text(structured, basics)
    title = basics.get("position") or structured.get("title", "岗位")
    h = structured.get("hard", {})
    soft = structured.get("soft", [])
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
    """岗位投放页主渲染：任职信息 → 已有 JD 拆解 → 生成 JD → 编辑发布。"""
    page_header("岗位创建", "选择岗位 → AI 生成初步画像 → 人工确认发布", "📌")

    _apply_form_seed()

    jd = load_jd() or {}
    if _legacy_weights(jd):
        st.info("检测到旧版二维权重，请重新保存后进入简历筛选。")

    basics0 = jd.get("basics", {}) or {}
    req0 = jd.get("requirements", {}) or {}
    h0 = req0.get("hard", {})

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
    _init("_jd_editor_visible", False)
    _init("jd_catalog_category", "当前岗位")
    _init("_jd_selected_job_applied", "")
    _init("_jd_generation_origin", jd.get("generation_origin", "人工录入"))

    # ── 岗位目录选择 + AI 自动生成 ───────────────────────────
    catalog_jobs = load_jobs()
    jobs_by_id = {job["id"]: job for job in catalog_jobs}
    # 页面文案严格按业务确认版本展示；内部仍兼容历史数据中的空格写法。
    category_options = [
        "当前岗位",
        "工程师/技术岗",
        "制造/工艺岗",
        "质量/IE方向",
        "职能/非技术岗",
        "高风险复核池",
    ]
    section("选择招聘岗位", "先选择岗位范围，再搜索具体岗位；选择后自动生成初步岗位画像")
    category_col, select_col, refresh_col = st.columns([1.35, 2.65, 1], gap="medium")
    with category_col:
        selected_category = st.selectbox(
            "岗位范围",
            options=category_options,
            key="jd_catalog_category",
        )

    data_category = (
        "质量/IE 方向" if selected_category == "质量/IE方向" else selected_category
    )

    if selected_category == "当前岗位":
        available_jobs = [job for job in catalog_jobs if job.get("id") == "published_jd"]
    else:
        available_jobs = [
            job for job in catalog_jobs
            if job.get("id") != "published_jd" and job.get("category") == data_category
        ]
    available_ids = [job["id"] for job in available_jobs]
    # 每个岗位范围使用独立控件状态，避免切换分类后残留上一类岗位。
    job_select_key = f"jd_catalog_job_id__{selected_category}"
    if st.session_state.get(job_select_key) not in ([""] + available_ids):
        st.session_state[job_select_key] = ""

    with select_col:
        selected_job_id = st.selectbox(
            "具体岗位",
            options=[""] + available_ids,
            format_func=lambda job_id: (
                ("当前没有已发布岗位" if selected_category == "当前岗位" else "搜索或选择具体岗位")
                if not job_id else jobs_by_id[job_id].get("title", "")
            ),
            key=job_select_key,
            disabled=not available_ids,
        )
    with refresh_col:
        st.caption("需要不同版本？")
        regenerate = st.button(
            "重新生成",
            use_container_width=True,
            disabled=not selected_job_id,
            key="regenerate_selected_job",
        )

    if selected_category == "高风险复核池":
        st.caption("高风险复核池用于候选人复核，不属于招聘岗位，因此不会生成 JD。")

    selection_changed = (
        selected_job_id
        and selected_job_id != st.session_state.get("_jd_selected_job_applied")
    )
    if selected_job_id and (selection_changed or regenerate):
        selected_job = jobs_by_id[selected_job_id]
        with st.status("正在生成岗位初步画像...", expanded=True) as status:
            status.write("读取企业岗位模板与岗位类别...")
            profile, used_ai = generate_job_profile(selected_job)
            basics, requirements = _profile_payload(profile)
            status.write("生成岗位描述、必备技能与软实力要求...")
            try:
                jd_text = generate_jd_text(requirements, basics)
            except Exception:
                jd_text = _local_jd_text(requirements, basics)
            origin = "AI 初步生成" if used_ai else "岗位模板初步生成"
            save_jd({
                "title": requirements["title"],
                "basics": basics,
                "requirements": requirements,
                "jd_text_generated": jd_text,
                "raw_text": selected_job.get("jd_text", ""),
                "source_job_id": selected_job_id,
                "generation_origin": origin,
                "generation_status": "draft",
                "role_summary": profile.get("role_summary", ""),
                "responsibilities": profile.get("responsibilities", []),
            })
            st.session_state["_jd_form_seed"] = _profile_form_seed(profile)
            st.session_state["_jd_selected_job_applied"] = selected_job_id
            st.session_state["_jd_generation_origin"] = origin
            st.session_state["_jd_editor_visible"] = True
            st.session_state["jd_text_edit"] = jd_text
            status.update(label=f"{origin}完成，请检查并修改", state="complete")
        st.rerun()

    if st.session_state.get("_jd_selected_job_applied"):
        origin = st.session_state.get("_jd_generation_origin", "初步生成")
        st.info(f"✨ **{origin}**　以下内容尚未发布，可由 HR 修改确认。")

    # ── 紧凑编辑区：基本信息 + 技能软实力 ───────────────────
    with st.container(border=True):
        basic_col, skill_col = st.columns([1.05, 0.95], gap="large")
        with basic_col:
            section("基本岗位信息", "AI 已带出初始值，可直接修改")
            r1a, r1b = st.columns(2)
            with r1a:
                st.text_input("岗位", key="jd_position", placeholder="例：质量工程师")
            with r1b:
                st.text_input("所属部门", key="jd_dept", placeholder="例：质量部")
            r2a, r2b = st.columns(2)
            with r2a:
                st.text_input("职级", key="jd_level", placeholder="例：P5 / T3")
            with r2b:
                st.text_input("工作地点", key="jd_location", placeholder="例：青岛")
            r3a, r3b, r3c = st.columns(3)
            with r3a:
                st.number_input("招聘人数", min_value=1, step=1, key="jd_count")
            with r3b:
                st.number_input("最低年限", min_value=0, step=1, key="jd_years")
            with r3c:
                st.text_input("学历", key="jd_degree", placeholder="本科")
            st.text_area("岗位目标与核心工作", key="jd_base_req", height=96)

        with skill_col:
            section("技能与软实力", "来源于岗位模板与 AI 岗位画像")
            st.text_area(
                "必备技能（逗号分隔）",
                key="jd_must",
                height=76,
                placeholder="例：ISO 9001, 8D, FMEA",
            )
            st.text_area(
                "加分技能（逗号分隔）",
                key="jd_nice",
                height=76,
                placeholder="例：六西格玛, APQP",
            )
            st.text_area(
                "软实力要求（逗号分隔）",
                key="jd_soft",
                height=76,
                placeholder="例：沟通协作, 数据分析, 抗压能力",
            )

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
                    s.write("正在拆解任职要求...")
                    try:
                        r = parse_jd(st.session_state["jd_raw"])
                    except Exception:
                        r = _local_parse_jd(st.session_state["jd_raw"])
                        s.write("模型暂不可用，已切换为本地规则拆解。")
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

    # ── 生成 JD ─────────────────────────────────────────────
    section("生成招聘 JD 描述", "AI 优先生成；未配置模型时自动使用本地模板")
    if st.button("📝 生成JD描述", type="primary", key="gen_jd_final"):
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
        with st.status("生成 JD 描述中...", expanded=True) as s:
            s.write("正在把结构化要求扩写为五段招聘文案...")
            try:
                jd_text = generate_jd_text(req, basics)
                s.update(label="JD 描述已生成", state="complete")
            except Exception:
                jd_text = _local_jd_text(req, basics)
                s.update(label="已使用本地模板生成，可继续编辑", state="complete")

        save_jd({
            "title": req["title"],
            "basics": basics,
            "requirements": req,
            "jd_text_generated": jd_text,
            "raw_text": st.session_state.get("jd_raw", ""),
            "source_job_id": jd.get("source_job_id", ""),
            "generation_origin": (
                "AI 初步生成"
                if settings.is_configured and not demo_mode_enabled()
                else "岗位模板初步生成"
            ),
            "generation_status": "draft",
        })
        st.session_state["_jd_generation_origin"] = (
            "AI 初步生成"
            if settings.is_configured and not demo_mode_enabled()
            else "岗位模板初步生成"
        )
        st.session_state["_jd_editor_visible"] = True
        st.success("已生成 JD 描述，可在下方查看并编辑")
        st.rerun()

    # 生成后直接在按钮下方展示初步 JD 描述，可编辑发布
    if st.session_state.get("_jd_editor_visible"):
        jd = load_jd() or {}
        jd_text = jd.get("jd_text_generated", "")
        if jd_text:
            section("初步 JD 文案", "AI 初步生成，可由 HR 微调后发布")
            req = jd.get("requirements", {})
            h = req.get("hard", {})
            basics = jd.get("basics", {}) or {}
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
            st.caption(line1)
            st.caption(line2)

            edited = st.text_area(
                "招聘文案（Markdown，可编辑）",
                value=jd_text,
                height=320,
                key="jd_text_edit",
            )
            if st.button("💾 发布JD", key="save_jd_text"):
                jd["jd_text_generated"] = edited
                jd["generation_status"] = "published"
                jd["confirmed_by"] = "HR 人工确认"
                save_jd(jd)
                st.session_state["current_job_id"] = "published_jd"
                st.success("已发布 JD，并设为当前筛选岗位")
                st.rerun()

            if st.button("进入简历筛选 →", type="primary", key="go_screening_after_jd"):
                st.session_state["current_job_id"] = "published_jd"
                st.session_state["_hirex_pending_screening_stage"] = "简历筛选"
                st.rerun()
