"""国际化（i18n）—— 中/英双语。

════════════════════════════════════════════════════════════════
 设计取舍
════════════════════════════════════════════════════════════════

★ 用【扁平 key + 单一字典】，不用嵌套结构。
  嵌套读起来漂亮，但取值要写 t("nav")["resume"]，一旦某层缺失就是
  KeyError/TypeError，而翻译缺失是最常见的情况。扁平 key + 缺失回退，
  界面永远不会因为漏翻一句话而崩。

★ 缺失时的回退顺序：当前语言 → 中文 → key 本身。
  **回退到 key 本身而不是空字符串** —— 空字符串会让漏翻表现为"这里本来
  就没内容"，而露出 key（如 `nav.settings`）一眼就能看出是漏翻了。
  让缺陷可见，是这个项目里反复出现的同一条原则。

★ 语言状态存在 st.session_state，不落盘。
  切语言是会话级偏好，不该改 .env —— 那会影响别人的会话。
"""

from __future__ import annotations

LANGUAGES = {"zh": "简体中文", "en": "English"}
DEFAULT_LANG = "zh"

_STRINGS: dict[str, dict[str, str]] = {
    # ── 品牌 / 导航 ──────────────────────────────
    "app.name":            {"zh": "智能招聘系统",   "en": "AI Recruiting"},
    "app.tagline":         {"zh": "简历分析 · AI 面试 · 评估报告",
                            "en": "Screening · AI Interview · Assessment"},
    "nav.analysis":        {"zh": "简历分析",       "en": "Screening"},
    "nav.interview":       {"zh": "AI 面试",        "en": "Interview"},
    "nav.report":          {"zh": "评估报告",       "en": "Report"},
    "nav.skills":          {"zh": "Skills",         "en": "Skills"},
    "nav.settings":        {"zh": "设置",           "en": "Settings"},

    # ── 简历分析 ────────────────────────────────
    "analysis.title":      {"zh": "简历智能分析",   "en": "Resume Analysis"},
    "analysis.subtitle":   {"zh": "JD 解析 · 匹配评分 · 试题生成 · 模糊点追问",
                            "en": "JD parsing · Match scoring · Question generation · Follow-ups"},
    "analysis.jd":         {"zh": "职位描述 (JD)",  "en": "Job Description"},
    "analysis.jd_hint":    {"zh": "PDF / DOCX / TXT，或用下方文本框直接粘贴",
                            "en": "PDF / DOCX / TXT, or paste below"},
    "analysis.resume":     {"zh": "候选人简历",     "en": "Candidate Resume"},
    "analysis.resume_hint":{"zh": "PDF / DOCX / TXT，支持中英文简历",
                            "en": "PDF / DOCX / TXT, Chinese & English supported"},
    "analysis.or":         {"zh": "或",             "en": "or"},
    "analysis.paste_jd":   {"zh": "直接粘贴 JD 文本", "en": "Paste JD text"},
    "analysis.paste_ph":   {"zh": "在此粘贴职位描述...", "en": "Paste the job description here..."},
    "analysis.start":      {"zh": "开始分析",       "en": "Start Analysis"},
    "analysis.reset":      {"zh": "重新分析",       "en": "Reset"},

    # ── 设置 ────────────────────────────────────
    "settings.title":      {"zh": "系统设置",       "en": "Settings"},
    "settings.subtitle":   {"zh": "语言 · 模型接入 · 语音引擎",
                            "en": "Language · Model API · Speech engine"},
    "settings.language":   {"zh": "界面语言",       "en": "Language"},
    "settings.model":      {"zh": "模型接入",       "en": "Model API"},
    "settings.provider":   {"zh": "服务商预设",     "en": "Provider preset"},
    "settings.base_url":   {"zh": "API 地址 (Base URL)", "en": "API Base URL"},
    "settings.model_name": {"zh": "模型名称",       "en": "Model name"},
    "settings.api_key":    {"zh": "API Key",        "en": "API Key"},
    "settings.key_kept":   {"zh": "已配置（保持不变）", "en": "Configured (unchanged)"},
    "settings.key_empty":  {"zh": "未配置",         "en": "Not configured"},
    "settings.test":       {"zh": "测试连接",       "en": "Test connection"},
    "settings.save":       {"zh": "保存到 .env",    "en": "Save to .env"},
    "settings.saved":      {"zh": "已保存，重启应用后生效",
                            "en": "Saved. Restart the app to take effect."},
    "settings.test_ok":    {"zh": "连接成功",       "en": "Connection OK"},
    "settings.test_fail":  {"zh": "连接失败",       "en": "Connection failed"},
    "settings.current":    {"zh": "当前生效配置",   "en": "Currently active"},
    "settings.speech":     {"zh": "语音引擎",       "en": "Speech engine"},
    "settings.engine_ok":  {"zh": "可用",           "en": "Available"},
    "settings.engine_no":  {"zh": "不可用",         "en": "Unavailable"},
    "settings.key_help":   {"zh": "留空则保留现有 Key，不会被清除",
                            "en": "Leave blank to keep the existing key"},

    # ── 简历分析：结果页 ─────────────────────────
    "analysis.upload_ready_hint": {"zh": "需要同时提供 JD（文件或文本）与简历文件",
                                   "en": "Provide both a JD (file or text) and a resume file"},
    "analysis.paste_label": {"zh": "或直接粘贴 JD 文本", "en": "Or paste the JD text"},
    "analysis.paste_hint":  {"zh": "没有文件？把职位描述粘贴到这里也可以…",
                             "en": "No file? Paste the job description here…"},
    "analysis.sample_hint": {"zh": "仓库自带可直接使用的示例：`test_resumes/示例简历-王思远-后端开发.txt`\n\n⚠️ 扫描件 / 图片型 PDF 需要额外安装 `rapidocr-onnxruntime` 才能识别。",
                             "en": "A ready-to-use sample ships with the repo: `test_resumes/示例简历-王思远-后端开发.txt`\n\n⚠️ Scanned / image-only PDFs need `rapidocr-onnxruntime` installed."},
    "analysis.spinner_parse": {"zh": "正在解析文档…", "en": "Parsing documents…"},
    "analysis.spinner_run":   {"zh": "Graph DAG 执行中（Harness 护栏 · Checker 校准 · Skills 扩展）…",
                               "en": "Running Graph DAG (Harness · Checker · Skills)…"},
    "analysis.parse_failed":  {"zh": "文档解析失败：", "en": "Document parsing failed: "},
    "analysis.empty_input":   {"zh": "JD 与简历内容都不能为空",
                               "en": "Both the JD and the resume must be non-empty"},
    "analysis.run_failed":    {"zh": "分析失败，请到「设置」页检查模型 API 配置",
                               "en": "Analysis failed — check the model API settings"},
    "analysis.session_lost":  {"zh": "会话数据在服务重启后丢失，需要重新分析。",
                               "en": "Session data was lost after a restart. Please re-run the analysis."},
    "analysis.verdict":       {"zh": "录用建议",       "en": "Recommendation"},
    "analysis.score_label":   {"zh": "综合匹配度",     "en": "Match score"},
    "analysis.target_role":   {"zh": "目标岗位",       "en": "Target role"},
    "analysis.candidate":     {"zh": "候选人",         "en": "Candidate"},
    "analysis.questions":     {"zh": "面试题",         "en": "Questions"},
    "analysis.q_count":       {"zh": "{n} 道",         "en": "{n}"},
    "analysis.dim_cover":     {"zh": "覆盖 {n} 个维度", "en": "{n} dimensions covered"},
    "analysis.checker":       {"zh": "Checker",        "en": "Checker"},
    "analysis.checker_pass":  {"zh": "已通过",         "en": "Passed"},
    "analysis.checker_deg":   {"zh": "已降级",         "en": "Degraded"},
    "analysis.checker_rounds":{"zh": "{n} 轮校准",     "en": "{n} calibration round(s)"},
    "analysis.evidence":      {"zh": "评分依据",       "en": "Scoring evidence"},
    "analysis.evidence_hint": {"zh": "每条理由都应能在简历/JD 原文中找到出处",
                               "en": "Every reason should be traceable to the resume or JD"},
    "analysis.no_breakdown":  {"zh": "模型未返回维度拆分", "en": "No dimension breakdown returned"},
    "analysis.strengths":     {"zh": "优势",           "en": "Strengths"},
    "analysis.gaps":          {"zh": "差距",           "en": "Gaps"},
    "analysis.risks":         {"zh": "风险",           "en": "Risks"},
    "analysis.no_strengths":  {"zh": "暂无匹配优势项", "en": "No strengths identified"},
    "analysis.no_gaps":       {"zh": "暂无差距项",     "en": "No gaps identified"},
    "analysis.no_risks":      {"zh": "暂无风险项",     "en": "No risks identified"},
    "analysis.materials":     {"zh": "面试材料",       "en": "Interview material"},
    "analysis.qbank":         {"zh": "面试题库（{n} 道）", "en": "Question bank ({n})"},
    "analysis.followups":     {"zh": "模糊点深度追问（{n} 组）",
                               "en": "Ambiguity follow-ups ({n} groups)"},
    "analysis.red_flag":      {"zh": "危险信号：",     "en": "Red flag: "},
    "analysis.engineering":   {"zh": "工程执行详情",   "en": "Engineering details"},
    "analysis.engineering_sub": {"zh": "Graph / Harness / Checker / Skills / 飞轮",
                                 "en": "Graph / Harness / Checker / Skills / Flywheel"},
    "analysis.make_link":     {"zh": "生成面试链接",   "en": "Create interview link"},
    "analysis.make_link_help":{"zh": "生成候选人专属链接，发过去即可独立完成 AI 面试",
                               "en": "Creates a candidate link for a self-serve AI interview"},
    "analysis.self_test":     {"zh": "自行测试面试",   "en": "Try the interview"},
    "analysis.relink":        {"zh": "重新生成链接",   "en": "Regenerate link"},
    "analysis.link_made":     {"zh": "面试链接已生成", "en": "Interview link created"},
    "analysis.link_expire":   {"zh": "有效期至",       "en": "valid until"},

    # ── 步骤条 ──────────────────────────────────
    "step.upload":    {"zh": "上传材料",  "en": "Upload"},
    "step.analyze":   {"zh": "智能分析",  "en": "Analyze"},
    "step.interview": {"zh": "AI 面试",   "en": "Interview"},
    "step.report":    {"zh": "评估报告",  "en": "Report"},

    # ── AI 面试 ─────────────────────────────────
    "interview.title":    {"zh": "AI 模拟面试", "en": "AI Mock Interview"},
    "interview.subtitle": {"zh": "多维度追问 · 数字人交互 · 实时评估",
                           "en": "Multi-dimensional probing · Avatar · Live assessment"},
    "interview.need_analysis":      {"zh": "请先完成简历分析", "en": "Run the resume analysis first"},
    "interview.need_analysis_desc": {"zh": "切换到「简历分析」，上传 JD 与简历后系统会自动生成面试题库",
                                     "en": "Go to Screening, upload a JD and a resume, and the question bank is generated automatically"},
    "interview.qbank_total": {"zh": "题库总量",   "en": "Question bank"},
    "interview.sample_n":    {"zh": "本次抽取",   "en": "Sampled"},
    "interview.sample_hint": {"zh": "可在左侧「设置」调整", "en": "Adjust in the sidebar"},
    "interview.match":       {"zh": "简历匹配度", "en": "Resume match"},
    "interview.brief":       {"zh": "系统将从 {total} 道题中随机抽取 {n} 道，并根据你的回答实时追问。面试过程可随时结束并生成报告。",
                              "en": "{n} of {total} questions will be sampled, with live follow-ups based on your answers. You can end the interview at any time."},
    "interview.preview":     {"zh": "题库预览",   "en": "Question preview"},
    "interview.preview_more":{"zh": "另有 {n} 道未展示", "en": "{n} more not shown"},
    "interview.start":       {"zh": "开始面试",   "en": "Start interview"},
    "interview.running":     {"zh": "面试中",     "en": "In progress"},
    "interview.ended":       {"zh": "已结束",     "en": "Ended"},
    "interview.round":       {"zh": "第 {i}/{n} 轮", "en": "Round {i}/{n}"},
    "interview.persona":     {"zh": "人格",       "en": "Persona"},
    "interview.covered":     {"zh": "已覆盖维度", "en": "Dimensions covered"},
    "interview.remaining":   {"zh": "题库剩余",   "en": "Questions left"},
    "interview.pending":     {"zh": "待覆盖",     "en": "Pending"},
    "interview.input_ph":    {"zh": "输入你的回答…", "en": "Type your answer…"},
    "interview.end_btn":     {"zh": "结束面试",   "en": "End interview"},
    "interview.done_msg":    {"zh": "面试已结束", "en": "Interview finished"},
    "interview.view_report": {"zh": "查看评估报告", "en": "View report"},
    "interview.thinking":    {"zh": "面试官思考中…", "en": "Interviewer is thinking…"},
    "interview.booting":     {"zh": "正在启动面试官…", "en": "Starting the interviewer…"},

    # ── 评估报告 ────────────────────────────────
    "report.title":     {"zh": "面试评估报告", "en": "Interview Assessment"},
    "report.subtitle":  {"zh": "五维雷达 · 逐题评审 · 录用建议",
                         "en": "Five-dimension radar · Per-question review · Recommendation"},
    "report.empty":     {"zh": "暂无评估报告", "en": "No report yet"},
    "report.empty_desc":{"zh": "完成「AI 面试」后，系统会自动生成多维度评估报告",
                         "en": "Finish the AI interview and the report is generated automatically"},
    "report.score":     {"zh": "综合评分",   "en": "Overall score"},
    "report.rounds":    {"zh": "面试轮数",   "en": "Rounds"},
    "report.dims":      {"zh": "评估维度",   "en": "Dimensions"},
    "report.highlights":{"zh": "亮点",       "en": "Highlights"},
    "report.concerns":  {"zh": "关注点",     "en": "Concerns"},
    "report.five_dim":  {"zh": "五维能力评估", "en": "Five-dimension assessment"},
    "report.hl_and_cn": {"zh": "亮点与关注点", "en": "Highlights and concerns"},
    "report.no_hl":     {"zh": "未识别到明显亮点", "en": "No notable highlights"},
    "report.no_cn":     {"zh": "未识别到明显关注点", "en": "No notable concerns"},
    "report.contradict":{"zh": "前后矛盾",   "en": "Contradictions"},
    "report.per_q":     {"zh": "逐题评审",   "en": "Per-question review"},
    "report.q_count":   {"zh": "共 {n} 题",  "en": "{n} questions"},
    "report.question":  {"zh": "问题",       "en": "Question"},
    "report.answer":    {"zh": "回答摘要",   "en": "Answer summary"},
    "report.comment":   {"zh": "评价",       "en": "Assessment"},
    "report.generating":{"zh": "正在生成报告…", "en": "Generating the report…"},
    "report.overall":   {"zh": "综合",       "en": "Overall"},

    # ── 录用建议 / 评估维度 ──────────────────────
    "rec.strong_hire": {"zh": "强烈推荐", "en": "Strong hire"},
    "rec.hire":        {"zh": "推荐录用", "en": "Hire"},
    "rec.hold":        {"zh": "待定",     "en": "Hold"},
    "rec.no_hire":     {"zh": "不推荐",   "en": "No hire"},
    "dim.job_match":            {"zh": "岗位匹配", "en": "Job fit"},
    "dim.technical_ability":    {"zh": "技术能力", "en": "Technical"},
    "dim.communication":        {"zh": "沟通表达", "en": "Communication"},
    "dim.comprehensive_quality":{"zh": "综合素质", "en": "Overall quality"},
    "dim.integrity":            {"zh": "诚信度",   "en": "Integrity"},
    "mdim.skills_match":      {"zh": "技能匹配", "en": "Skills"},
    "mdim.experience_match":  {"zh": "经验匹配", "en": "Experience"},
    "mdim.education_match":   {"zh": "学历匹配", "en": "Education"},
    "mdim.project_relevance": {"zh": "项目相关", "en": "Projects"},
    "report.round_n":  {"zh": "第 {n} 轮", "en": "Round {n}"},
    "report.score_n":  {"zh": "{n} 分",    "en": "{n} pts"},

    # ── 通用 ────────────────────────────────────
    "common.model":        {"zh": "模型",           "en": "Model"},
    "common.tts":          {"zh": "语音",           "en": "TTS"},
    "common.rounds":       {"zh": "面试题数",       "en": "Questions"},
    "common.settings":     {"zh": "设置",           "en": "Settings"},
    "common.reset_session":{"zh": "重置会话",       "en": "Reset session"},
    "common.tts_toggle":   {"zh": "TTS 语音播报",   "en": "Voice playback"},
    "common.avatar":       {"zh": "虚拟主播",       "en": "Virtual host"},
}


def get_lang() -> str:
    """当前语言。读 st.session_state；非 Streamlit 环境下回退默认值。"""
    try:
        import streamlit as st
        return st.session_state.get("ui_lang", DEFAULT_LANG)
    except Exception:  # noqa: BLE001
        return DEFAULT_LANG


def set_lang(lang: str) -> None:
    import streamlit as st
    st.session_state["ui_lang"] = lang if lang in LANGUAGES else DEFAULT_LANG


def t(key: str, **fmt) -> str:
    """取翻译。缺失时回退 中文 → key 本身（让漏翻可见，而不是显示空白）。"""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(get_lang()) or entry.get(DEFAULT_LANG) or key
    return text.format(**fmt) if fmt else text


def missing_report() -> dict[str, list[str]]:
    """哪些 key 缺了哪个语种。

    ★ 提供这个函数是为了让"翻译完整度"可被检查，而不是靠人逐屏点。
      没有它，漏翻只会在用户切到英文时才暴露 —— 而那通常是演示现场。
    """
    out: dict[str, list[str]] = {lang: [] for lang in LANGUAGES}
    for key, entry in _STRINGS.items():
        for lang in LANGUAGES:
            if not entry.get(lang):
                out[lang].append(key)
    return {k: v for k, v in out.items() if v}
