"""人才评价汇总、人才库复用与 Offer 应急补位页面。"""

from copy import deepcopy

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from app.shared import list_candidates, load_jd, update_candidate
from app.talent_pool import (
    RADAR_DIMENSIONS,
    comparison_rows,
    decision_score,
    display_stage,
    generate_talent_profile,
    interview_score,
    is_pool_qualified,
    jd_signature,
    overall_score,
    radar_scores,
    recommend_backups,
    talent_tag_labels,
)
from app.ui.components import esc, pill


TEAL = "#00a69c"
NAVY = "#173e58"
RADAR_COLORS = [TEAL, "#4e84aa", "#e4a13a"]
RISK_COLORS = {"低": "#10a874", "中": "#e59a24", "高": "#df4d4d", "未检测": "#91a0ae"}

# 仅供比赛演示页面使用，不回写候选人 JSON。正式数据由面试辅助模块写入。
DEMO_INTERVIEWS = {
    "cand_001": {
        "rating": "A",
        "dimension_scores": {"专业能力": 94, "问题解决": 91, "协作沟通": 87, "岗位动机": 89},
        "summary": "专业深度和复杂项目经验突出，回答有量化证据，建议作为首选人推进。",
    },
    "cand_002": {
        "rating": "B+",
        "dimension_scores": {"专业能力": 76, "问题解决": 72, "协作沟通": 82, "岗位动机": 80},
        "summary": "基础能力和稳定性较好，复杂场景经验偏弱，适合作为培养型备选人才。",
    },
    "cand_003": {
        "rating": "C",
        "dimension_scores": {"专业能力": 61, "问题解决": 58, "协作沟通": 65, "岗位动机": 54},
        "summary": "经历断层解释和项目证据不足，当前不建议推进，需保留正式背调结论。",
    },
}


def _view_candidates(candidates):
    """补充只存在于页面内存中的面试演示结果。"""
    result = deepcopy(candidates)
    for candidate in result:
        if not candidate.get("interview_eval") and candidate.get("id") in DEMO_INTERVIEWS:
            candidate["interview_eval"] = DEMO_INTERVIEWS[candidate["id"]]
            candidate["_demo_interview"] = True
    return result


def _profile(candidate):
    parsed = candidate.get("resume_parsed") or {}
    experience = (parsed.get("experience") or [{}])[0]
    education = (parsed.get("education") or [{}])[0]
    return {
        "company": experience.get("company", "经历待完善"),
        "title": experience.get("title", "岗位待完善"),
        "education": f"{education.get('school', '院校待完善')} · {education.get('degree', '学历待完善')}",
        "years": f"{parsed.get('total_years', '-')}年经验",
    }


def _top_candidate(candidates):
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: decision_score(candidate) or overall_score(candidate))


def _radar(candidates, height=330):
    ordered = sorted(candidates, key=lambda candidate: decision_score(candidate) or overall_score(candidate), reverse=True)[:3]
    dimensions = list(RADAR_DIMENSIONS)
    figure = go.Figure()
    for index, candidate in enumerate(ordered):
        scores = radar_scores(candidate)
        values = [scores[dimension] for dimension in dimensions]
        figure.add_trace(
            go.Scatterpolar(
                r=values + values[:1],
                theta=dimensions + dimensions[:1],
                fill="toself",
                line=dict(color=RADAR_COLORS[index], width=2),
                marker=dict(size=5),
                opacity=0.72,
                name=candidate.get("name", candidate.get("id", "候选人")),
            )
        )
    figure.update_layout(
        height=height,
        margin=dict(l=28, r=28, t=16, b=16),
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(246,250,252,.8)",
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9, color="#9aa8b4")),
            angularaxis=dict(tickfont=dict(size=12, color=NAVY)),
        ),
        legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center", font=dict(size=11)),
    )
    return figure


def _context_bar(candidates):
    jd = load_jd() or {}
    left, middle, right = st.columns([2.2, 1, 1])
    left.selectbox("当前岗位", [jd.get("title", "当前招聘岗位")], label_visibility="collapsed")
    middle.selectbox("招聘部门", ["技术与质量中心"], label_visibility="collapsed")
    right.button("导出决策报告", use_container_width=True)
    st.markdown(
        f'<div class="talent-context"><span class="context-dot"></span>已汇总 <b>{len(candidates)}</b> 位候选人的简历、风险与面试结果；所有AI建议均保留人工确认入口。</div>',
        unsafe_allow_html=True,
    )


def _decision_overview(candidates):
    top = _top_candidate(candidates)
    top_name = top.get("name", "待确认") if top else "待确认"
    top_score = decision_score(top) if top else None
    qualified = [candidate for candidate in candidates if is_pool_qualified(candidate)]
    low_risk = sum((candidate.get("risk_report") or {}).get("level") == "低" for candidate in candidates)
    interviewed = sum(bool(candidate.get("interview_eval")) for candidate in candidates)
    jd = load_jd() or {}

    left, center, right = st.columns([1.02, 1.25, 1.18], gap="medium")
    with left:
        with st.container(border=True):
            st.markdown('<div class="panel-title">岗位与候选人概览 <span>实时汇总</span></div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="job-facts">
                  <div><span>招聘岗位</span><b>{esc(jd.get('title', '当前岗位'))}</b></div>
                  <div><span>招聘部门</span><b>技术与质量中心</b></div>
                  <div><span>面试完成</span><b>{interviewed} / {len(candidates)} 人</b></div>
                  <div><span>当前阶段</span><b>用人部门决策</b></div>
                </div>
                <div class="hero-score"><small>首选人综合决策分</small><strong>{esc(top_score if top_score is not None else '-')}</strong><span>/100</span><p>{esc(top_name)} · AI建议优先推进</p></div>
                """,
                unsafe_allow_html=True,
            )
    with center:
        with st.container(border=True):
            st.markdown('<div class="panel-title">候选人能力对比雷达图 <span>TOP 3</span></div>', unsafe_allow_html=True)
            st.plotly_chart(_radar(candidates), use_container_width=True, config={"displayModeBar": False})
    with right:
        with st.container(border=True):
            st.markdown(f'<div class="panel-title">AI整体决策建议 {pill("建议复核", "brand")}</div>', unsafe_allow_html=True)
            top_summary = ((top or {}).get("interview_eval") or {}).get("summary", "请结合匹配、风险与面试证据完成人工复核。")
            st.markdown(
                f'<div class="ai-decision"><b>建议首选：{esc(top_name)}</b><p>{esc(top_summary)}</p></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="decision-stats">
                  <div><b>{len(qualified)}</b><span>合格人才</span></div>
                  <div><b>{low_risk}</b><span>低风险</span></div>
                  <div><b>{max(0, len(qualified)-1)}</b><span>可用备选</span></div>
                </div>
                <div class="decision-line"><span>首选依据</span><b>专业能力、项目复杂度与面试证据领先</b></div>
                <div class="decision-line"><span>人工确认点</span><b>薪资期望、到岗周期及背调结果</b></div>
                """,
                unsafe_allow_html=True,
            )


def _confirm(candidate, candidates):
    jd = load_jd() or {}
    update_candidate(candidate["id"], "status", "offered")
    pooled = []
    for other in candidates:
        if other.get("id") == candidate.get("id") or not is_pool_qualified(other):
            continue
        update_candidate(other["id"], "talent_profile", generate_talent_profile(other, jd))
        update_candidate(other["id"], "status", "in_pool")
        pooled.append(other.get("name", other["id"]))
    st.session_state["talent_notification"] = f"已确认 {candidate.get('name')} 为首选人并模拟推送；另有 {len(pooled)} 位合格人才自动标签入库。"
    st.rerun()


def _mark(candidate, value):
    update_candidate(candidate["id"], "hr_decision", value)
    st.session_state["talent_notification"] = f"已记录 {candidate.get('name')} 的人工结论：{value}。"
    st.rerun()


def _select_detail(candidate_id):
    st.session_state["talent_detail_id"] = candidate_id
    st.session_state["talent_detail_level"] = 1
    st.session_state["talent_scroll_detail"] = True
    st.session_state.pop("talent_dimension_key", None)
    st.session_state.pop("talent_subdimension_index", None)
    st.session_state.pop("talent_tag_focus", None)


def _close_detail():
    st.session_state.pop("talent_detail_id", None)
    st.session_state.pop("talent_detail_level", None)
    st.session_state.pop("talent_dimension_key", None)
    st.session_state.pop("talent_subdimension_index", None)
    st.session_state.pop("talent_tag_focus", None)
    st.session_state.pop("talent_candidate_switch", None)
    st.session_state["talent_scroll_list"] = True


def _switch_detail_candidate():
    candidate_id = st.session_state.get("talent_candidate_switch")
    if candidate_id:
        _select_detail(candidate_id)


def _scroll_page_top(flag):
    """页面状态切换后，将 Streamlit 主滚动区稳定复位到顶部。"""
    if not st.session_state.pop(flag, False):
        return
    components.html(
        """
        <script>
        const resetTop = () => {
          const main = window.parent.document.querySelector('.stMain');
          if (main) main.scrollTo({top: 0, left: 0, behavior: 'auto'});
          window.parent.scrollTo({top: 0, left: 0, behavior: 'auto'});
        };
        resetTop();
        setTimeout(resetTop, 80);
        setTimeout(resetTop, 240);
        setTimeout(resetTop, 700);
        </script>
        """,
        height=0,
    )


def _open_dimension(dimension_key):
    st.session_state["talent_dimension_key"] = dimension_key
    st.session_state["talent_detail_level"] = 2
    st.session_state["talent_scroll_detail"] = True
    st.session_state.pop("talent_subdimension_index", None)


def _open_evidence(subdimension_index):
    st.session_state["talent_subdimension_index"] = subdimension_index
    st.session_state["talent_detail_level"] = 3
    st.session_state["talent_scroll_detail"] = True


def _open_tag_evidence(candidate_id, category_key, tag_index):
    """从人才库标签直接进入对应证据，不经过能力总览。"""
    st.session_state["talent_detail_id"] = candidate_id
    st.session_state["talent_detail_level"] = 3
    st.session_state["talent_tag_focus"] = {"category": category_key, "index": tag_index}
    st.session_state.pop("talent_dimension_key", None)
    st.session_state.pop("talent_subdimension_index", None)
    st.session_state["talent_scroll_detail"] = True


def _detail_back():
    if st.session_state.pop("talent_tag_focus", None):
        st.session_state["talent_detail_level"] = 1
        st.session_state["talent_scroll_detail"] = True
        return
    level = st.session_state.get("talent_detail_level", 1)
    if level >= 3:
        st.session_state["talent_detail_level"] = 2
        st.session_state.pop("talent_subdimension_index", None)
    else:
        st.session_state["talent_detail_level"] = 1
        st.session_state.pop("talent_dimension_key", None)
    st.session_state["talent_scroll_detail"] = True


def _safe_average(*values):
    numbers = [float(value) for value in values if value is not None and value != ""]
    return round(sum(numbers) / len(numbers)) if numbers else 0


def _score_tone(score):
    if score >= 85:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "中等"
    return "待提升"


def _candidate_evidence(candidate):
    """把现有结构化结果整理成统一八维模型，所有展示证据均保留来源。"""
    parsed = candidate.get("resume_parsed") or {}
    match = candidate.get("match_result") or {}
    breakdown = match.get("breakdown") or {}
    interview = candidate.get("interview_eval") or {}
    interview_dims = interview.get("dimension_scores") or {}
    risks = (candidate.get("risk_report") or {}).get("risks") or []

    def metric(key, fallback=0):
        return float((breakdown.get(key) or {}).get("score", fallback) or fallback)

    def reason(key, fallback="当前材料未提供明确依据"):
        return (breakdown.get(key) or {}).get("reason") or fallback

    education = parsed.get("education") or []
    experiences = parsed.get("experience") or []
    skills = parsed.get("skills") or []
    education_quote = "；".join(
        f"{item.get('school', '院校待完善')}·{item.get('degree', '学历待完善')}·{item.get('major', '专业待完善')}"
        for item in education[:2]
    ) or "简历未提供完整教育信息"
    experience_quote = "；".join(
        f"{item.get('company', '公司待完善')}·{item.get('title', '岗位待完善')}（{item.get('start', '?')}—{item.get('end', '?')}）"
        for item in experiences[:3]
    ) or "简历未提供完整工作经历"
    skills_quote = "、".join(skills[:12]) or "简历未列出明确技能"
    matched_quote = "；".join(match.get("matched_points") or []) or "暂无明确匹配证据"
    gaps_quote = "；".join(match.get("gap_points") or []) or "暂无明确差距证据"
    interview_quote = interview.get("summary") or "尚未完成结构化面试评价"
    risk_quote = "；".join(
        f"{item.get('type', '待核验')}：{item.get('evidence') or item.get('detail') or '待人工核验'}"
        for item in risks[:3]
    ) or "未发现明确履历异常线索，仍需按企业流程完成背调"

    skills_score = metric("skills_match")
    experience_score = metric("experience_match")
    education_score = metric("education_match")
    project_score = metric("project_relevance")
    hard_score = float(match.get("hard_score", 0) or 0)
    soft_score = float(match.get("soft_score", 0) or 0)
    professional_score = float(interview_dims.get("专业能力", 0) or 0)
    problem_score = float(interview_dims.get("问题解决", 0) or 0)
    collaboration_score = float(interview_dims.get("协作沟通", 0) or 0)
    motivation_score = float(interview_dims.get("岗位动机", 0) or 0)
    risk_level = (candidate.get("risk_report") or {}).get("level", "未检测")
    stability_score = {"低": 88, "中": 65, "高": 35}.get(risk_level, 60)

    def ev(source, quote, interpretation, confidence="高", action="无需额外核验"):
        return {
            "source": source,
            "quote": quote,
            "interpretation": interpretation,
            "confidence": confidence,
            "action": action,
        }

    return {
        "qualification": {
            "icon": "▣", "title": "基础资质", "score": round(education_score), "weight": 10,
            "summary": reason("education_match"),
            "subdimensions": [
                {"label": "学历门槛", "score": round(education_score), "basis": "核对学历层次与JD硬性要求", "evidence": [ev("简历·教育经历", education_quote, reason("education_match"))]},
                {"label": "专业相关性", "score": round(_safe_average(education_score, hard_score)), "basis": "结合所学专业与岗位方向判断", "evidence": [ev("简历·教育经历", education_quote, "专业信息已提取，最终相关性需结合岗位要求复核", "中", "由HR确认专业放宽规则")]},
                {"label": "证书资质", "score": None, "basis": "当前材料未形成有效证书证据", "evidence": [ev("简历·证书信息", "未检索到可验证证书记录", "证据不足，不计入加分", "低", "面试时要求提供证书编号及有效期")]},
            ],
        },
        "expertise": {
            "icon": "◇", "title": "专业知识与技能", "score": round(_safe_average(skills_score, professional_score or None)), "weight": 20,
            "summary": reason("skills_match"),
            "subdimensions": [
                {"label": "核心技能覆盖", "score": round(skills_score), "basis": "JD核心技能与简历技能交叉匹配", "evidence": [ev("简历·技能清单", skills_quote, reason("skills_match"))]},
                {"label": "技能实操深度", "score": round(professional_score) if professional_score else None, "basis": "优先采用结构化面试专业能力得分", "evidence": [ev("面试·评价表", interview_quote, f"专业能力评价：{professional_score:.0f}分" if professional_score else "尚无面试实操证据", "高" if professional_score else "低", "围绕核心技能增加实操追问")]},
                {"label": "工具与方法应用", "score": round(_safe_average(skills_score, project_score)), "basis": "技能是否在相关项目场景中出现", "evidence": [ev("简历·技能及项目", f"技能：{skills_quote}；项目判断：{reason('project_relevance')}", "存在技能与场景的关联，个人使用深度仍需核验", "中", "要求候选人说明工具选择与实际产出")]},
            ],
        },
        "experience": {
            "icon": "▤", "title": "岗位与行业经验", "score": round(experience_score), "weight": 15,
            "summary": reason("experience_match"),
            "subdimensions": [
                {"label": "相关岗位年限", "score": round(experience_score), "basis": "根据起止时间与岗位名称计算", "evidence": [ev("简历·工作经历", experience_quote, reason("experience_match"))]},
                {"label": "行业场景适配", "score": round(_safe_average(experience_score, project_score)), "basis": "工作场景与当前岗位业务复杂度对照", "evidence": [ev("简历·经历与项目", f"{experience_quote}；{reason('project_relevance')}", "具备可迁移经验，行业细节仍需用人部门判断", "中", "追问同类业务场景的处理方法")]},
                {"label": "职责复杂度", "score": round(_safe_average(experience_score, problem_score or None)), "basis": "综合经历描述与面试问题解决表现", "evidence": [ev("简历+面试", f"{reason('experience_match')}；{interview_quote}", "复杂任务承担程度由多源材料交叉判断", "中", "核实其在团队中的真实职责边界")]},
            ],
        },
        "achievement": {
            "icon": "◎", "title": "项目与业绩成果", "score": round(project_score), "weight": 15,
            "summary": reason("project_relevance"),
            "subdimensions": [
                {"label": "成果相关性", "score": round(project_score), "basis": "项目内容与JD核心任务匹配", "evidence": [ev("简历·项目经历", reason("project_relevance"), reason("project_relevance"))]},
                {"label": "成果量化程度", "score": round(_safe_average(project_score, soft_score)), "basis": "检查是否给出规模、效率、质量等结果", "evidence": [ev("简历·匹配证据", matched_quote, "已识别成果线索；没有数字的成果不作强结论", "中", "要求补充基线、结果与测量口径")]},
                {"label": "个人贡献清晰度", "score": None, "basis": "现有简历无法完整区分团队成果与个人贡献", "evidence": [ev("简历·项目描述", matched_quote, "证据不足，暂不单独加分", "低", "面试使用STAR法核实候选人个人动作")]},
            ],
        },
        "problem_solving": {
            "icon": "⌁", "title": "问题分析与解决", "score": round(problem_score or _safe_average(project_score, soft_score)), "weight": 15,
            "summary": "结合项目复杂度、面试回答与结果证据评估问题解决能力。",
            "subdimensions": [
                {"label": "问题拆解", "score": round(problem_score) if problem_score else None, "basis": "来自结构化面试问题解决维度", "evidence": [ev("面试·评价表", interview_quote, f"问题解决得分：{problem_score:.0f}" if problem_score else "暂无有效面试证据", "高" if problem_score else "低", "用情景题核验分析步骤")]},
                {"label": "方案判断", "score": round(_safe_average(problem_score or None, project_score)), "basis": "结合项目方案和面试决策逻辑", "evidence": [ev("简历+面试", f"{reason('project_relevance')}；{interview_quote}", "AI进行跨材料一致性判断", "中", "追问备选方案与取舍依据")]},
                {"label": "复盘改进", "score": None, "basis": "当前材料未提供清晰复盘案例", "evidence": [ev("简历+面试", gaps_quote, "证据不足，需通过追问补齐", "低", "追问一次失败经历及后续改进")]},
            ],
        },
        "execution": {
            "icon": "↗", "title": "执行与协作", "score": round(collaboration_score or soft_score), "weight": 10,
            "summary": "结合面试协作沟通得分与简历软性证据形成初步判断。",
            "subdimensions": [
                {"label": "目标执行", "score": round(_safe_average(soft_score, project_score)), "basis": "从成果完成度与软性匹配侧面判断", "evidence": [ev("简历·成果与软性匹配", f"{matched_quote}；{match.get('summary', '')}", "可见执行线索，但仍需区分个人贡献", "中", "核实目标、动作和实际结果")]},
                {"label": "跨部门协作", "score": round(collaboration_score) if collaboration_score else None, "basis": "优先采用结构化面试协作沟通得分", "evidence": [ev("面试·评价表", interview_quote, f"协作沟通得分：{collaboration_score:.0f}" if collaboration_score else "暂无协作行为证据", "高" if collaboration_score else "低", "追问一次跨部门冲突处理案例")]},
                {"label": "沟通表达", "score": round(collaboration_score) if collaboration_score else None, "basis": "根据面试回答的结构与清晰度评价", "evidence": [ev("面试·评价表", interview_quote, "当前为面试官结构化评价结果", "中", "由面试官复核AI纪要与原话")]},
            ],
        },
        "learning": {
            "icon": "△", "title": "学习与适应", "score": round(_safe_average(soft_score, problem_score or None, skills_score)), "weight": 10,
            "summary": "依据技能迁移、问题解决和软性匹配形成可验证的潜力判断。",
            "subdimensions": [
                {"label": "新知应用", "score": round(_safe_average(skills_score, project_score)), "basis": "技能是否在项目中形成应用闭环", "evidence": [ev("简历·技能及项目", f"{skills_quote}；{reason('project_relevance')}", "存在学习应用线索，不等同于掌握深度", "中", "追问最近一次快速学习并落地的经历")]},
                {"label": "快速适应", "score": round(soft_score), "basis": "采用软性素质匹配结果作为初筛信号", "evidence": [ev("AI匹配·软性维度", f"软性匹配得分 {soft_score:.0f}；{match.get('summary', '')}", "仅为初筛信号，不能替代行为面试", "中", "用岗位变化情景题进行核验")]},
                {"label": "成长潜力", "score": round(_safe_average(soft_score, problem_score or None)), "basis": "综合软性匹配和解决问题表现", "evidence": [ev("简历+面试", interview_quote, "AI形成初步潜力判断", "中", "由用人部门结合岗位培养周期确认")]},
            ],
        },
        "motivation": {
            "icon": "◉", "title": "职业动机与稳定性", "score": round(_safe_average(motivation_score or None, stability_score)), "weight": 5,
            "summary": "结合岗位动机、履历连续性和风险线索评估，风险提示不等同于事实认定。",
            "subdimensions": [
                {"label": "求职动机", "score": round(motivation_score) if motivation_score else None, "basis": "来自结构化面试岗位动机维度", "evidence": [ev("面试·评价表", interview_quote, f"岗位动机得分：{motivation_score:.0f}" if motivation_score else "尚无动机证据", "高" if motivation_score else "低", "确认离职原因与职业目标")]},
                {"label": "岗位意愿", "score": round(motivation_score) if motivation_score else None, "basis": "结合面试意愿表达形成初步判断", "evidence": [ev("面试·评价表", interview_quote, "意愿仍需结合薪资、地点和到岗时间人工确认", "中", "由HR电话初面确认关键意愿")]},
                {"label": "职业稳定性", "score": stability_score, "basis": "根据履历连续性和风险规则计算", "evidence": [ev("简历·履历风险", risk_quote, f"当前风险等级：{risk_level}；仅作为待核验线索", "高" if risks else "中", "按企业流程完成背调与时间线核验")]},
            ],
        },
    }


def _ability_scores(candidate):
    """统一简历匹配与面试评价，形成可解释的八维能力画像。"""
    radar = radar_scores(candidate)
    interview = (candidate.get("interview_eval") or {}).get("dimension_scores") or {}
    return {
        "核心技能": radar.get("技能", 0),
        "相关经验": radar.get("经验", 0),
        "学历基础": radar.get("学历", 0),
        "项目成果": radar.get("项目", 0),
        "专业能力": float(interview.get("专业能力", 0) or 0),
        "问题解决": float(interview.get("问题解决", 0) or 0),
        "协作沟通": float(interview.get("协作沟通", 0) or 0),
        "岗位动机": float(interview.get("岗位动机", 0) or 0),
    }


def _detail_radar(candidate):
    scores = _ability_scores(candidate)
    labels = list(scores)
    values = list(scores.values())
    benchmark = [75] * len(labels)
    figure = go.Figure()
    figure.add_trace(go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1], fill="toself",
        name="候选人", line=dict(color=TEAL, width=2), opacity=.75,
    ))
    figure.add_trace(go.Scatterpolar(
        r=benchmark + benchmark[:1], theta=labels + labels[:1],
        name="岗位基准", line=dict(color="#e59a24", width=2, dash="dash"),
    ))
    figure.update_layout(
        height=390, margin=dict(l=35, r=35, t=20, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(bgcolor="#f7fbfb", radialaxis=dict(visible=True, range=[0, 100])),
        legend=dict(orientation="h", y=-.08, x=.5, xanchor="center"),
    )
    return figure


def _dimension_radar(dimensions, selected_key=None):
    labels = [item["title"] for item in dimensions.values()]
    values = [item["score"] or 0 for item in dimensions.values()]
    benchmark = [75] * len(labels)
    figure = go.Figure()
    figure.add_trace(go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1], fill="toself",
        name="候选人", line=dict(color=TEAL, width=2.5), opacity=.72,
    ))
    figure.add_trace(go.Scatterpolar(
        r=benchmark + benchmark[:1], theta=labels + labels[:1],
        name="岗位基准", line=dict(color="#e4a13a", width=2, dash="dash"),
    ))
    figure.update_layout(
        height=360, margin=dict(l=45, r=45, t=20, b=35), paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(bgcolor="#f7fbfb", radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9))),
        legend=dict(orientation="h", y=-.10, x=.5, xanchor="center"),
    )
    return figure


def _detail_header(candidate, level, title, candidates):
    profile = _profile(candidate)
    steps = ["1 能力总览", "2 维度分析", "3 证据溯源"]
    head, switcher, actions = st.columns([4.8, 1.55, 1.8], vertical_alignment="center")
    head.markdown(
        f'<div class="detail-head"><small>候选人AI能力档案 · {esc(title)}</small>'
        f'<b>{esc(candidate.get("name", candidate["id"]))}</b>'
        f'<span>{esc(profile["company"])} · {esc(profile["title"])}　｜　{esc(profile["education"])}　｜　{esc(profile["years"])}</span></div>',
        unsafe_allow_html=True,
    )
    candidate_ids = [item["id"] for item in candidates]
    current_index = candidate_ids.index(candidate["id"])
    switcher.selectbox(
        "切换候选人",
        candidate_ids,
        index=current_index,
        format_func=lambda candidate_id: next(
            (item.get("name", candidate_id) for item in candidates if item["id"] == candidate_id),
            candidate_id,
        ),
        key="talent_candidate_switch",
        on_change=_switch_detail_candidate,
    )
    back, close = actions.columns(2)
    if level > 1:
        back.button("返回上层", use_container_width=True, on_click=_detail_back)
    close.button("关闭档案", use_container_width=True, on_click=_close_detail)
    st.markdown(
        '<div class="detail-steps">' + "".join(
            f'<span class="{"active" if index == level else "done" if index < level else ""}">{esc(step)}</span>'
            for index, step in enumerate(steps, 1)
        ) + '<i>每个AI结论都可逐层追溯到原始材料</i></div>',
        unsafe_allow_html=True,
    )


def _detail_overview(candidate, dimensions):
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    interview = candidate.get("interview_eval") or {}
    d_score = decision_score(candidate) or overall_score(candidate)
    risk_level = risk.get("level", "未检测")
    st.markdown(
        f"""
        <div class="detail-kpis">
          <div><small>综合决策分</small><b>{esc(d_score)}</b><span>匹配、面试与风险加权</span></div>
          <div><small>人岗匹配</small><b>{esc(match.get('overall_score', '-'))}</b><span>硬性 {esc(match.get('hard_score', '-'))} / 软性 {esc(match.get('soft_score', '-'))}</span></div>
          <div><small>面试表现</small><b>{esc(interview_score(candidate) or '-')}</b><span>评级 {esc(interview.get('rating', '待评'))}</span></div>
          <div><small>风险等级</small><b style="color:{RISK_COLORS.get(risk_level, '#91a0ae')}">{esc(risk_level)}</b><span>{len(risk.get('risks') or [])} 个待核验点</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    radar_col, ai_col = st.columns([1.25, 1], gap="medium")
    with radar_col:
        st.markdown('<div class="detail-panel-title">八维能力画像 <span class="ai-mark">AI动态评估</span></div>', unsafe_allow_html=True)
        st.plotly_chart(_dimension_radar(dimensions), use_container_width=True, config={"displayModeBar": False})
    with ai_col:
        st.markdown('<div class="detail-panel-title">整体人才评语 <span class="ai-mark">AI生成</span></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="detail-ai"><b>{esc(match.get("recommendation", "建议人工复核"))}</b>'
            f'<p>{esc(interview.get("summary") or match.get("summary") or "等待AI汇总。")}</p>'
            f'<small>◎ AI综合评价 · 依据简历、风险报告与面试评价</small></div>',
            unsafe_allow_html=True,
        )
        good_count = sum((item["score"] or 0) >= 75 for item in dimensions.values())
        missing_count = sum(any(sub["score"] is None for sub in item["subdimensions"]) for item in dimensions.values())
        st.markdown(
            f'<div class="ai-summary-grid"><div><b>{good_count}</b><span>达标维度</span></div>'
            f'<div><b>{missing_count}</b><span>存在待核验项</span></div>'
            f'<div><b>75</b><span>岗位参考线</span></div></div>',
            unsafe_allow_html=True,
        )
        st.caption("AI评分用于辅助决策；最终结论由HR与用人部门确认。")

    st.markdown('<div class="talent-section"><b>八维能力概览</b><span>点击任一能力卡进入专项分析</span></div>', unsafe_allow_html=True)
    items = list(dimensions.items())
    for row_start in range(0, len(items), 4):
        columns = st.columns(4, gap="medium")
        for column, (key, item) in zip(columns, items[row_start:row_start + 4]):
            with column:
                with st.container(border=True):
                    score = item["score"] or 0
                    known = sum(sub["score"] is not None for sub in item["subdimensions"])
                    st.markdown(
                        f'<div class="ability-card"><div class="ability-card-head"><span>{esc(item["icon"])} {esc(item["title"])}</span>'
                        f'<em>{esc(item["weight"])}%权重</em></div><div class="ability-score"><b>{esc(score)}</b><small>/100</small>'
                        f'<i>{esc(_score_tone(score))}</i></div><div class="ability-progress"><span style="width:{max(0, min(100, score))}%"></span></div>'
                        f'<p>{esc(item["summary"])}</p><small class="ability-source">◎ AI评估 · {known}/3项有依据</small></div>',
                        unsafe_allow_html=True,
                    )
                    st.button(
                        "查看维度详情 →", key=f"ability_{candidate['id']}_{key}", use_container_width=True,
                        on_click=_open_dimension, args=(key,),
                    )


def _dimension_detail(candidate, dimension_key, dimension):
    left, center, right = st.columns([1, 1.35, 1.1], gap="medium")
    score = dimension["score"] or 0
    with left:
        st.markdown(
            f'<div class="dimension-score"><small>{esc(dimension["title"])}综合评分</small>'
            f'<b>{esc(score)}</b><span>/100</span><em>{esc(_score_tone(score))}</em>'
            f'<p>岗位权重 {dimension["weight"]}% · 参考线75分</p></div>', unsafe_allow_html=True,
        )
        for sub in dimension["subdimensions"]:
            value = sub["score"]
            display = "待核验" if value is None else f"{value}分"
            width = 0 if value is None else value
            st.markdown(
                f'<div class="sub-score"><span>{esc(sub["label"])}</span><b>{esc(display)}</b>'
                f'<div><i style="width:{width}%"></i></div></div>', unsafe_allow_html=True,
            )
    with center:
        st.markdown('<div class="detail-panel-title">子维度达成情况 <span class="ai-mark">AI拆解</span></div>', unsafe_allow_html=True)
        labels = [sub["label"] for sub in dimension["subdimensions"]]
        values = [sub["score"] or 0 for sub in dimension["subdimensions"]]
        figure = go.Figure(go.Scatterpolar(
            r=values + values[:1], theta=labels + labels[:1], fill="toself",
            line=dict(color=TEAL, width=2.5), opacity=.75,
        ))
        figure.add_trace(go.Scatterpolar(
            r=[75, 75, 75, 75], theta=labels + labels[:1],
            line=dict(color="#e4a13a", dash="dash"), name="岗位基准",
        ))
        figure.update_layout(
            height=350, margin=dict(l=45, r=45, t=20, b=20), showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)", polar=dict(bgcolor="#f7fbfb", radialaxis=dict(range=[0, 100], visible=True)),
        )
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown('<div class="detail-panel-title">维度评价 <span class="ai-mark">AI生成</span></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="detail-ai"><p>{esc(dimension["summary"])}</p>'
            f'<small>◎ AI专项评价 · 可进入下方证据页复核</small></div>', unsafe_allow_html=True,
        )
        known = [sub for sub in dimension["subdimensions"] if sub["score"] is not None]
        missing = [sub for sub in dimension["subdimensions"] if sub["score"] is None]
        st.markdown(f"**已形成依据：** {len(known)} 项")
        st.markdown(f"**待补充核验：** {len(missing)} 项")
        if missing:
            st.warning("、".join(sub["label"] for sub in missing) + "证据不足，当前不计入强推荐。")

    st.markdown('<div class="talent-section"><b>子维度与评价依据</b><span>继续点击可查看原始材料、AI解释和核验动作</span></div>', unsafe_allow_html=True)
    for index, sub in enumerate(dimension["subdimensions"]):
        with st.container(border=True):
            info, basis, evidence, action = st.columns([1.1, 2.2, 1, 1.15], vertical_alignment="center")
            value = sub["score"]
            info.markdown(f'**{esc(sub["label"])}**')
            info.caption("待核验" if value is None else f"AI评分 {value}分 · {_score_tone(value)}")
            basis.markdown(f'<div class="sub-basis"><span>评价口径</span><p>{esc(sub["basis"])}</p></div>', unsafe_allow_html=True)
            evidence.metric("证据条数", len(sub["evidence"]))
            action.button(
                "查看证据链 →", key=f"evidence_{candidate['id']}_{dimension_key}_{index}",
                type="primary" if value is None else "secondary", use_container_width=True,
                on_click=_open_evidence, args=(index,),
            )


def _evidence_detail(candidate, dimension, subdimension):
    value = subdimension["score"]
    score_label = "待核验" if value is None else f"{value}分"
    st.markdown(
        f'<div class="evidence-hero"><div><small>{esc(dimension["title"])} / {esc(subdimension["label"])}</small>'
        f'<b>{esc(score_label)}</b><span>{esc("证据不足，暂不计入强推荐" if value is None else _score_tone(value))}</span></div>'
        f'<p><strong>AI评分口径</strong>{esc(subdimension["basis"])}</p>'
        f'<em>◎ AI证据链 · 原始材料 → 信息提取 → 能力判断 → 下一步动作</em></div>',
        unsafe_allow_html=True,
    )
    for index, evidence in enumerate(subdimension["evidence"], 1):
        with st.container(border=True):
            source_col, inference_col = st.columns([1.2, 1], gap="large")
            with source_col:
                st.markdown(f'<div class="source-label">证据 {index} · {esc(evidence["source"])}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="source-quote">“{esc(evidence["quote"])}”</div>', unsafe_allow_html=True)
                st.caption("以上内容来自候选人材料或已提交评价；正式接入后可定位到原简历段落/面试时间点。")
            with inference_col:
                st.markdown('<div class="source-label">AI如何使用这条证据</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="ai-inference"><p>{esc(evidence["interpretation"])}</p>'
                            f'<small>◎ AI证据解读 · 置信度 {esc(evidence["confidence"])}</small></div>', unsafe_allow_html=True)
                st.markdown(f"**建议动作：** {evidence['action']}")
    st.markdown(
        '<div class="trace-chain"><div><b>① 原始材料</b><span>简历 / 面试 / 风险报告</span></div>'
        '<i>→</i><div><b>② AI信息抽取</b><span>事实与待核验线索</span></div><i>→</i>'
        '<div><b>③ 能力判断</b><span>按岗位口径评分</span></div><i>→</i>'
        '<div><b>④ 人工确认</b><span>追问、修改或采纳</span></div></div>',
        unsafe_allow_html=True,
    )


def _current_talent_profile(candidate, persist=False):
    """读取当前 JD 下的人才档案；JD 变化后自动重算。"""
    jd = load_jd() or {}
    stored = candidate.get("talent_profile") or {}
    if stored.get("jd_signature") == jd_signature(jd) and stored.get("categories"):
        return stored
    generated = generate_talent_profile(candidate, jd)
    candidate["talent_profile"] = generated
    if persist:
        update_candidate(candidate["id"], "talent_profile", generated)
    return generated


def _focused_tag(profile, focus):
    for category in profile.get("categories") or []:
        if category.get("key") != focus.get("category"):
            continue
        tags = category.get("tags") or []
        index = focus.get("index", 0)
        if isinstance(index, int) and 0 <= index < len(tags):
            return category, tags[index]
    return None, None


def _tag_evidence_detail(category, tag, profile):
    priority = profile.get("reuse_priority") or {}
    components = priority.get("components") or {}
    st.markdown(
        f'<div class="evidence-hero"><div><small>{esc(category.get("label", "人才标签"))}</small>'
        f'<b style="font-size:32px">{esc(tag.get("label", "-"))}</b><span>置信度 {esc(tag.get("confidence", "-"))}%</span></div>'
        f'<p><strong>AI标签判断</strong>{esc(tag.get("reason", "根据候选人材料生成。"))}</p>'
        f'<em>◎ AI自动标签 · 点击标签直达原始依据</em></div>',
        unsafe_allow_html=True,
    )
    source_col, inference_col = st.columns([1.2, 1], gap="large")
    with source_col:
        st.markdown(f'<div class="source-label">标签依据 · {esc(tag.get("source", "候选人材料"))}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="source-quote">“{esc(tag.get("evidence", "暂无可用证据"))}”</div>', unsafe_allow_html=True)
        st.caption("该内容来自当前JD、候选人简历或已提交面试评价；正式接入后可定位原文段落。")
    with inference_col:
        st.markdown('<div class="source-label">当前岗位复用计算</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ai-inference"><p>{esc(priority.get("explanation", "根据当前岗位动态计算。"))}</p>'
            f'<small>◎ AI辅助判断 · 仍由HR确认</small></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="reuse-components"><div><b>{esc(components.get("当前JD匹配", "-"))}</b><span>当前JD匹配·60%</span></div>'
            f'<div><b>{esc(components.get("历史面试", "-"))}</b><span>历史面试·25%</span></div>'
            f'<div><b>{esc(components.get("证据完整度", "-"))}</b><span>证据完整·15%</span></div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="trace-chain"><div><b>① 当前JD/人才档案</b><span>岗位要求与历史材料</span></div>'
        '<i>→</i><div><b>② AI事实抽取</b><span>仅提取有材料支撑的信息</span></div><i>→</i>'
        '<div><b>③ 自动生成标签</b><span>岗位、技能、经验、能力</span></div><i>→</i>'
        '<div><b>④ 动态复用排序</b><span>换岗位后重新计算</span></div></div>',
        unsafe_allow_html=True,
    )


def _detail_report(candidate, candidates):
    tag_focus = st.session_state.get("talent_tag_focus")
    if tag_focus:
        profile = _current_talent_profile(candidate)
        category, tag = _focused_tag(profile, tag_focus)
        if category and tag:
            with st.container(border=True):
                _detail_header(candidate, 3, "标签依据", candidates)
                _tag_evidence_detail(category, tag, profile)
            return
        st.session_state.pop("talent_tag_focus", None)
    dimensions = _candidate_evidence(candidate)
    level = st.session_state.get("talent_detail_level", 1)
    dimension_key = st.session_state.get("talent_dimension_key")
    if dimension_key not in dimensions:
        level = 1
    title = "八维能力总览"
    if level >= 2 and dimension_key in dimensions:
        title = dimensions[dimension_key]["title"]
    with st.container(border=True):
        _detail_header(candidate, level, title, candidates)
        if level == 1:
            _detail_overview(candidate, dimensions)
        elif level == 2:
            _dimension_detail(candidate, dimension_key, dimensions[dimension_key])
        else:
            subdimensions = dimensions[dimension_key]["subdimensions"]
            sub_index = st.session_state.get("talent_subdimension_index", 0)
            if not isinstance(sub_index, int) or not 0 <= sub_index < len(subdimensions):
                sub_index = 0
            _evidence_detail(candidate, dimensions[dimension_key], subdimensions[sub_index])


def _candidate_card(candidate, rank, all_candidates):
    profile = _profile(candidate)
    match = candidate.get("match_result") or {}
    risk = candidate.get("risk_report") or {}
    interview = candidate.get("interview_eval") or {}
    risk_level = risk.get("level", "未检测")
    score = decision_score(candidate) or overall_score(candidate)

    with st.container(border=True):
        identity, decision_col, interview_col, risk_col = st.columns([2.9, 1, 1, 1], vertical_alignment="center")
        identity.markdown(
            f'<div class="candidate-name"><span class="rank-no">{rank}</span><div><b>{esc(candidate.get("name", candidate["id"]))}</b><small>{esc(profile["company"])} · {esc(profile["title"])}</small></div></div>',
            unsafe_allow_html=True,
        )
        identity.caption(f'{profile["education"]}　｜　{profile["years"]}　｜　{display_stage(candidate)}')
        identity.markdown(" ".join(pill(tag, "neutral") for tag in (candidate.get("tags") or [])[:4]), unsafe_allow_html=True)
        decision_col.markdown(f'<div class="candidate-metric"><b>{esc(score)}</b><span>综合决策分</span></div>', unsafe_allow_html=True)
        interview_col.markdown(f'<div class="candidate-metric"><b>{esc(interview_score(candidate) or "-")}</b><span>面试分 · {esc(interview.get("rating", "待评"))}</span></div>', unsafe_allow_html=True)
        risk_col.markdown(f'<div class="candidate-metric"><b style="color:{RISK_COLORS.get(risk_level, "#91a0ae")}">{esc(risk_level)}</b><span>风险等级</span></div>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="candidate-conclusion"><span>AI综合结论</span><p>{esc(interview.get("summary") or match.get("summary") or "等待AI汇总。")}</p><b>人工状态：{esc(candidate.get("hr_decision") or "待确认")}</b></div>',
            unsafe_allow_html=True,
        )
        with st.expander("查看评分依据、短板与风险证据"):
            strengths, gaps, risks = st.columns(3)
            strengths.markdown("**匹配优势**")
            for point in match.get("matched_points") or ["暂无"]:
                strengths.markdown(f"- {point}")
            gaps.markdown("**主要短板**")
            for point in match.get("gap_points") or ["暂无"]:
                gaps.markdown(f"- {point}")
            risks.markdown("**风险证据**")
            risk_items = risk.get("risks") or [{"type": "暂无明显风险", "detail": "仍需完成正式背调"}]
            for item in risk_items:
                risks.markdown(f"- **{item.get('type')}**：{item.get('detail', '')}")

        detail, primary, hold, reject, pool = st.columns([1.35, 1, 1, 1, 1])
        detail.button(
            "查看详细能力报告", key=f"detail_{candidate['id']}",
            use_container_width=True, on_click=_select_detail, args=(candidate["id"],),
        )
        if primary.button("确认为首选", key=f"primary_{candidate['id']}", type="primary", use_container_width=True):
            _confirm(candidate, all_candidates)
        if hold.button("待定", key=f"hold_{candidate['id']}", use_container_width=True):
            _mark(candidate, "待定")
        if reject.button("不推进", key=f"reject_{candidate['id']}", use_container_width=True):
            _mark(candidate, "不推进")
        if pool.button("加入人才库", key=f"pool_{candidate['id']}", use_container_width=True, disabled=not is_pool_qualified(candidate)):
            update_candidate(candidate["id"], "talent_profile", generate_talent_profile(candidate, load_jd() or {}))
            update_candidate(candidate["id"], "status", "in_pool")
            st.session_state["talent_notification"] = f"{candidate.get('name')} 已自动标签入库。"
            st.rerun()


def _decision_tab(candidates):
    _decision_overview(candidates)
    st.markdown('<div class="talent-section"><b>候选人横向决策</b><span>统一汇总匹配、风险与面试结果</span></div>', unsafe_allow_html=True)
    st.dataframe(comparison_rows(candidates), use_container_width=True, hide_index=True)
    st.markdown('<div class="talent-section"><b>候选人决策卡</b><span>AI提供依据，最终结论由HR和用人部门确认</span></div>', unsafe_allow_html=True)
    ordered = sorted(candidates, key=lambda candidate: decision_score(candidate) or overall_score(candidate), reverse=True)
    for rank, candidate in enumerate(ordered, 1):
        _candidate_card(candidate, rank, candidates)


def _reactivate(candidate):
    update_candidate(candidate["id"], "status", "screened")
    st.session_state["talent_notification"] = f"已重新激活 {candidate.get('name')}，并模拟推送给当前岗位HR复核。"
    st.rerun()


def _talent_tag_buttons(candidate, talent_profile):
    """四类标签固定布局；点击任一标签直接查看生成依据。"""
    categories = talent_profile.get("categories") or []
    if not categories:
        st.caption("暂无可生成标签的有效材料。")
        return
    st.markdown('<div class="tag-guide">AI自动入库标签 <span>点击标签，直接查看生成依据</span></div>', unsafe_allow_html=True)
    columns = st.columns(4, gap="small")
    for column, category in zip(columns, categories):
        with column:
            st.markdown(f'<div class="tag-category">{esc(category.get("label", "标签"))}</div>', unsafe_allow_html=True)
            tags = category.get("tags") or []
            if not tags:
                st.caption("待补充")
            for index, tag in enumerate(tags):
                st.button(
                    tag.get("label", "待补充"),
                    key=f"tag_{candidate['id']}_{category.get('key')}_{index}",
                    help="点击直达该标签的原始依据",
                    use_container_width=True,
                    on_click=_open_tag_evidence,
                    args=(candidate["id"], category.get("key"), index),
                )


def _pool_tab(candidates):
    talent_pool = [candidate for candidate in candidates if candidate.get("status") == "in_pool" or is_pool_qualified(candidate)]
    for candidate in talent_pool:
        _current_talent_profile(candidate, persist=True)
    st.markdown(
        f'<div class="reuse-banner"><div><small>人才库智能复用</small><b>系统已找到 {len(talent_pool)} 位可复用候选人</b><p>新岗位发布后，AI重新计算复用优先级；历史面试评价和标签依据继续保留。</p></div><span>当前JD动态排序</span></div>',
        unsafe_allow_html=True,
    )
    filters = st.columns([1.6, 1, 1, 1.2])
    keyword = filters[0].text_input("人才搜索", placeholder="姓名、技能或标签", label_visibility="collapsed")
    score_filter = filters[1].selectbox("匹配分", ["不限分数", "60分以上", "75分以上", "85分以上"], label_visibility="collapsed")
    filters[2].selectbox("风险", ["全部风险", "低风险", "中风险"], label_visibility="collapsed")
    filters[3].selectbox("来源", ["全部来源", "历史面试合格", "合格未录用"], label_visibility="collapsed")
    threshold = {"不限分数": 0, "60分以上": 60, "75分以上": 75, "85分以上": 85}[score_filter]
    visible = [candidate for candidate in talent_pool if overall_score(candidate) >= threshold]
    if keyword:
        visible = [
            candidate for candidate in visible
            if keyword.lower() in (
                candidate.get("name", "")
                + " ".join(candidate.get("tags") or [])
                + " ".join(talent_tag_labels(candidate.get("talent_profile") or {}))
            ).lower()
        ]
    if not visible:
        st.info("当前筛选条件下暂无可复用人才。")
    for candidate in sorted(visible, key=overall_score, reverse=True):
        profile = _profile(candidate)
        match = candidate.get("match_result") or {}
        talent_profile = candidate.get("talent_profile") or _current_talent_profile(candidate)
        priority = talent_profile.get("reuse_priority") or {}
        with st.container(border=True):
            info, score_col, reason, action = st.columns([2.5, 1, 2.2, 1.2], vertical_alignment="center")
            info.markdown(f"### {candidate.get('name', candidate['id'])}")
            info.caption(f'{profile["company"]} · {profile["title"]}　｜　{profile["education"]}')
            info.caption(f'历史匹配 {int(overall_score(candidate))} 分 · {display_stage(candidate)}')
            score_col.markdown(
                f'<div class="reuse-priority"><small>当前岗位复用优先级</small><b>{esc(priority.get("score", "-"))}</b><span>{esc(priority.get("level", "待计算"))}</span></div>',
                unsafe_allow_html=True,
            )
            reason.markdown("**AI复用建议**")
            reason.caption(priority.get("explanation") or match.get("summary", "历史评价完整，可重新联系。"))
            action.button(
                "查看人才档案", key=f"pool_detail_{candidate['id']}",
                use_container_width=True, on_click=_select_detail, args=(candidate["id"],),
            )
            if action.button("重新激活", key=f"reactivate_{candidate['id']}", type="primary", use_container_width=True):
                _reactivate(candidate)
            _talent_tag_buttons(candidate, talent_profile)


def _offer_tab(candidates):
    offered = [candidate for candidate in candidates if candidate.get("status") == "offered"]
    declined_id = st.session_state.get("declined_candidate_id")
    if offered:
        names = {candidate["id"]: candidate.get("name", candidate["id"]) for candidate in offered}
        st.markdown('<div class="offer-monitor"><span class="pulse"></span><div><b>Offer状态监听正常</b><small>状态变化后立即启动备选人才排序与推送</small></div></div>', unsafe_allow_html=True)
        selected_id = st.selectbox("已发Offer候选人", list(names), format_func=lambda candidate_id: names[candidate_id])
        if st.button("模拟候选人放弃Offer", type="primary"):
            update_candidate(selected_id, "status", "declined")
            st.session_state["declined_candidate_id"] = selected_id
            st.session_state["talent_notification"] = f"{names[selected_id]} 已放弃Offer；备选汇总表已推送给HR和用人部门。"
            st.rerun()
    elif not declined_id:
        top = _top_candidate(candidates)
        st.info("尚未发出Offer。请先在“选人决策”中确认首选人，再演示自动补位。")
        if top and st.button(f"快速演示：确认 {top.get('name')} 为首选人", type="primary"):
            _confirm(top, candidates)

    if declined_id:
        refreshed = _view_candidates(list_candidates())
        declined = next((candidate for candidate in refreshed if candidate.get("id") == declined_id), {})
        backups = recommend_backups(refreshed, declined_id)
        st.markdown(
            f'<div class="offer-alert"><small>Offer异常事件</small><b>{esc(declined.get("name", "首选人"))} 已放弃Offer</b><p>AI已完成备选人才重新排序，并模拟推送给HR与用人部门。</p></div>',
            unsafe_allow_html=True,
        )
        if backups:
            best = backups[0]
            st.success(f"建议优先联系：{best.get('name')}，匹配分 {int(overall_score(best))}，风险等级 {(best.get('risk_report') or {}).get('level', '未检测')}。")
            st.dataframe(comparison_rows(backups), use_container_width=True, hide_index=True)
            for index, candidate in enumerate(backups[:3], 1):
                with st.container(border=True):
                    info, reason, actions = st.columns([1.2, 3, 1.2], vertical_alignment="center")
                    info.markdown(f"**备选 {index} · {candidate.get('name')}**")
                    info.caption(f"综合决策分：{decision_score(candidate) or overall_score(candidate)}")
                    reason.markdown(f"**推荐依据：** {(candidate.get('interview_eval') or {}).get('summary') or (candidate.get('match_result') or {}).get('summary', '')}")
                    actions.button(
                        "查看详细报告", key=f"backup_detail_{candidate['id']}",
                        use_container_width=True, on_click=_select_detail, args=(candidate["id"],),
                    )
                    if actions.button("推进该候选人", key=f"backup_push_{candidate['id']}", type="primary", use_container_width=True):
                        update_candidate(candidate["id"], "status", "offered")
                        st.session_state["talent_notification"] = f"已选择 {candidate.get('name')} 继续推进。"
                        st.rerun()
        else:
            st.warning("当前没有满足条件的合格备选人才。")


def render():
    _styles()
    raw_candidates = list_candidates()
    if not raw_candidates:
        st.warning("暂无候选人数据，请先完成简历导入与筛选。")
        return
    candidates = _view_candidates(raw_candidates)
    detail_id = st.session_state.get("talent_detail_id")
    detail_candidate = next((candidate for candidate in candidates if candidate.get("id") == detail_id), None)
    if detail_candidate:
        _scroll_page_top("talent_scroll_detail")
        _detail_report(detail_candidate, candidates)
        return

    _scroll_page_top("talent_scroll_list")
    qualified_count = sum(is_pool_qualified(candidate) for candidate in candidates)
    interviewed_count = sum(bool(candidate.get("interview_eval")) for candidate in candidates)
    st.markdown(
        f"""
        <div class="talent-page-head">
          <div class="talent-page-copy">
            <b>人才评价与选人决策</b>
            <span>汇总简历、风险与面试证据，支持人才复用和 Offer 流失自动补位</span>
          </div>
          <div class="talent-head-stats">
            <div><b>{len(candidates)}</b><span>候选人</span></div>
            <div><b>{interviewed_count}</b><span>完成面试</span></div>
            <div><b>{qualified_count}</b><span>合格人才</span></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    notice = st.session_state.pop("talent_notification", None)
    if notice:
        st.success(f"✓ {notice}")
    _context_bar(candidates)
    if any(candidate.get("_demo_interview") for candidate in candidates):
        st.markdown('<div class="demo-note">演示说明：当前面试评分为人才评价页展示数据；真实流程由“面试辅助”提交评价后自动同步。</div>', unsafe_allow_html=True)
    decision, pool, offer = st.tabs(["选人决策", "人才库复用", "Offer应急补位"])
    with decision:
        _decision_tab(candidates)
    with pool:
        _pool_tab(candidates)
    with offer:
        _offer_tab(candidates)


def _styles():
    st.markdown(
        """
        <style>
        :root{--hx-teal:#00a69c;--hx-navy:#173e58;--hx-pale:#eaf7f6;--hx-line:#dbe8eb}
        .talent-page-head{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:4px 2px 15px;margin:0 0 4px;background:transparent;border:0;border-bottom:1px solid var(--hx-line);border-radius:0;box-shadow:none}
        .talent-page-copy>b{display:block;color:var(--hx-navy);font-size:20px;line-height:1.25;letter-spacing:-.015em}.talent-page-copy>span{display:block;color:#71858f;font-size:11px;margin-top:5px}
        .talent-head-stats{display:flex;align-items:center;flex-shrink:0}.talent-head-stats>div{min-width:70px;padding:2px 13px;text-align:center;border-left:1px solid #dfe9ea}.talent-head-stats b{display:block;color:var(--hx-navy);font-size:18px;line-height:1.1}.talent-head-stats span{font-size:9px;color:#8799a1}
        .demo-note{font-size:10px;color:#748890;background:transparent;border:0;border-left:2px solid #b8d9d6;border-radius:0;padding:2px 8px;margin:1px 0 8px}
        .talent-context{display:flex;align-items:center;gap:8px;padding:10px 14px;border:1px solid #cbe5e3;background:#effaf8;color:#58727c;border-radius:12px;font-size:12px;margin:4px 0 16px}.talent-context b{color:var(--hx-teal)}
        .context-dot{width:8px;height:8px;border-radius:50%;background:var(--hx-teal);box-shadow:0 0 0 4px rgba(0,166,156,.12)}
        [data-testid="stTabs"] [role="tablist"]{gap:20px!important;background:transparent!important;padding:0 2px!important;margin:10px 0 16px!important;border-radius:0!important;border-bottom:1px solid #dce7e9!important;width:100%!important;box-sizing:border-box!important;overflow:visible!important}
        [data-testid="stTabs"] [data-testid="stTab"]{height:39px!important;border-radius:0!important;padding:0 8px!important;color:#607781!important;font-weight:650!important;border:0!important;box-sizing:border-box!important}
        [data-testid="stTabs"] [aria-selected="true"]{background:transparent!important;color:var(--hx-teal)!important;box-shadow:inset 0 -3px 0 var(--hx-teal)!important}
        [data-testid="stTabs"] [aria-selected="true"] *{color:var(--hx-teal)!important}[data-testid="stTabs"] .react-aria-SelectionIndicator{display:none!important}
        [data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-color:var(--hx-line)!important;border-radius:18px!important;box-shadow:0 7px 22px rgba(33,76,91,.07)}
        .panel-title{display:flex;justify-content:space-between;align-items:center;color:var(--hx-navy);font-size:15px;font-weight:700;margin:2px 0 12px}.panel-title>span{font-size:10px;color:#8ca1a9;font-weight:500}
        .job-facts>div{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid #edf3f4;font-size:12px}.job-facts span{color:#83969e}.job-facts b{color:var(--hx-navy)}
        .hero-score{text-align:center;margin:18px 14px 14px;padding:20px 16px 18px;border-radius:13px;background:#f2faf9;border:0;box-shadow:inset 0 0 0 1px rgba(0,166,156,.08)}.hero-score small{display:block;color:#7c9299}.hero-score strong{font-size:46px;color:var(--hx-teal);line-height:1.1}.hero-score span{color:#97a8ae}.hero-score p{font-size:12px;color:var(--hx-navy);font-weight:650;margin:6px 0 0}
        .ai-decision{padding:13px 15px;border-radius:13px;background:#eff8f8;border-left:4px solid var(--hx-teal)}.ai-decision b{color:var(--hx-navy);font-size:14px}.ai-decision p{font-size:12px;color:#5f747e;line-height:1.65;margin:7px 0 0}
        .decision-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:13px 0}.decision-stats div{text-align:center;padding:10px 4px;background:#f7fafb;border-radius:11px}.decision-stats b{display:block;color:var(--hx-teal);font-size:22px}.decision-stats span{font-size:10px;color:#8799a0}
        .decision-line{padding:8px 0;border-top:1px dashed #dce8ea}.decision-line span{display:block;color:#8a9da4;font-size:10px}.decision-line b{display:block;color:#536c76;font-size:11px;margin-top:3px}
        .talent-section{display:flex;align-items:baseline;gap:10px;margin:25px 2px 12px}.talent-section b{font-size:17px;color:var(--hx-navy)}.talent-section span{font-size:11px;color:#91a1a8}
        .candidate-name{display:flex;align-items:center;gap:11px}.rank-no{width:29px;height:29px;display:flex;align-items:center;justify-content:center;border-radius:9px;background:#e5f6f4;color:var(--hx-teal);font-weight:800}.candidate-name b{display:block;color:var(--hx-navy);font-size:17px}.candidate-name small{display:block;color:#7f929a;font-size:11px;margin-top:3px}
        .candidate-metric{text-align:center;border-left:1px solid #e3edef}.candidate-metric b{display:block;color:var(--hx-teal);font-size:27px}.candidate-metric span{font-size:10px;color:#879aa2}
        .candidate-conclusion{display:grid;grid-template-columns:90px 1fr auto;align-items:center;gap:12px;margin:14px 0;padding:12px 14px;background:#f6fafb;border-radius:12px}.candidate-conclusion span{font-size:11px;color:#81949c}.candidate-conclusion p{margin:0;color:#526b75;font-size:12px;line-height:1.55}.candidate-conclusion b{font-size:11px;color:#2f6f91}
        .reuse-banner{display:flex;align-items:center;justify-content:space-between;padding:20px 22px;margin:15px 0;background:linear-gradient(120deg,#e6f7f4,#f9fcfc);border:1px solid #bfe3df;border-radius:17px}.reuse-banner small{display:block;color:#779097}.reuse-banner b{display:block;color:var(--hx-navy);font-size:19px;margin-top:3px}.reuse-banner p{margin:6px 0 0;font-size:12px}.reuse-banner>span{padding:7px 12px;border-radius:999px;background:#fff;color:var(--hx-teal);font-size:11px;border:1px solid #bfe3df}
        .reuse-priority{text-align:center;padding:9px 6px;border-radius:12px;background:#eff9f8;border:1px solid #d2ebe8}.reuse-priority small{display:block;color:#718991;font-size:9px}.reuse-priority b{display:block;color:var(--hx-teal);font-size:30px;line-height:1.15;margin:3px 0}.reuse-priority span{display:inline-block;color:#247e78;background:#dff4f1;border-radius:999px;padding:2px 8px;font-size:10px}
        .tag-guide{display:flex;align-items:center;gap:10px;margin:14px 0 7px;padding-top:12px;border-top:1px solid #e7eff0;color:var(--hx-navy);font-size:12px;font-weight:700}.tag-guide span{font-size:10px;color:#8a9da4;font-weight:400}.tag-category{margin:2px 0 6px;color:#71868e;font-size:10px;font-weight:700;letter-spacing:.04em}.reuse-components{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:12px}.reuse-components div{text-align:center;padding:10px 5px;background:#f6fafb;border:1px solid #e1ecee;border-radius:10px}.reuse-components b{display:block;color:var(--hx-teal);font-size:18px}.reuse-components span{display:block;color:#84979e;font-size:9px;margin-top:2px}
        .offer-monitor{display:flex;align-items:center;gap:12px;padding:14px 17px;margin:15px 0;border:1px solid #cfe5e4;background:#f4fbfa;border-radius:14px}.offer-monitor b{display:block;color:var(--hx-navy)}.offer-monitor small{display:block;color:#80949c;font-size:11px;margin-top:3px}.pulse{width:10px;height:10px;border-radius:50%;background:var(--hx-teal);box-shadow:0 0 0 6px rgba(0,166,156,.12)}
        .offer-alert{padding:18px 20px;margin:16px 0;background:#fff6ed;border:1px solid #f4ccaa;border-left:5px solid #e78934;border-radius:14px}.offer-alert small{display:block;color:#b6763b}.offer-alert b{display:block;color:#873f20;font-size:19px;margin:3px 0}.offer-alert p{margin:0;font-size:12px;color:#8f664f}
        .detail-head small{display:block;color:var(--hx-teal);font-size:10px;letter-spacing:.08em}.detail-head b{display:block;color:var(--hx-navy);font-size:25px;margin-top:2px}.detail-head span{display:block;color:#768b94;font-size:12px;margin-top:4px}
        .detail-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}.detail-kpis>div{padding:13px 15px;background:#f6fafb;border:1px solid #e2edef;border-radius:13px}.detail-kpis small{display:block;color:#82969e}.detail-kpis b{display:block;color:var(--hx-teal);font-size:28px;line-height:1.15;margin:3px 0}.detail-kpis span{font-size:10px;color:#94a5ab}
        .detail-panel-title{font-size:14px;color:var(--hx-navy);font-weight:700;margin:7px 0 13px}.ability-bar{display:grid;grid-template-columns:62px 1fr 28px;align-items:center;gap:8px;margin:10px 0}.ability-bar>span{font-size:11px;color:#657b84}.ability-bar>div{height:7px;border-radius:99px;background:#e6eff0;overflow:hidden}.ability-bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--hx-teal),#4e96a9)}.ability-bar b{font-size:11px;color:var(--hx-navy);text-align:right}
        .detail-ai{padding:14px;border-radius:13px;background:#eff9f8;border-left:4px solid var(--hx-teal);margin-bottom:13px}.detail-ai b{color:var(--hx-navy);font-size:15px}.detail-ai p{font-size:12px;color:#58717b;line-height:1.65;margin:7px 0 0}.detail-subtitle{font-size:14px;color:var(--hx-navy);font-weight:700;margin:14px 0 10px}
        .detail-ai small{display:block;text-align:right;color:#8ca0a9;font-size:10px;margin-top:10px}.ai-mark{float:right;padding:3px 8px;border-radius:999px;background:#e8f7f5;color:#23857f!important;font-size:10px!important;font-weight:500!important}
        .detail-steps{display:flex;align-items:center;gap:8px;margin:16px 0;padding:9px;background:#f1f6f7;border-radius:12px}.detail-steps span{padding:7px 13px;border-radius:9px;color:#8799a0;font-size:11px;font-weight:650}.detail-steps span.active{background:linear-gradient(135deg,var(--hx-teal),#16869a);color:white;box-shadow:0 5px 12px rgba(0,166,156,.18)}.detail-steps span.done{background:#dff3f1;color:#268b86}.detail-steps i{margin-left:auto;color:#8a9ea6;font-size:10px;font-style:normal;padding-right:7px}
        .ai-summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:13px 0}.ai-summary-grid div{text-align:center;padding:12px 5px;background:#f7fafb;border:1px solid #e5edef;border-radius:11px}.ai-summary-grid b{display:block;color:var(--hx-teal);font-size:23px}.ai-summary-grid span{font-size:10px;color:#82949b}
        .ability-card{min-height:207px}.ability-card-head{display:flex;align-items:center;justify-content:space-between;color:var(--hx-navy);font-weight:750;font-size:13px}.ability-card-head em{font-size:9px;font-style:normal;color:var(--hx-teal);background:#e7f7f5;padding:3px 6px;border-radius:999px}.ability-score{display:flex;align-items:baseline;gap:4px;margin:14px 0 8px}.ability-score b{font-size:37px;line-height:1;color:var(--hx-teal)}.ability-score small{color:#9aabb0}.ability-score i{margin-left:auto;font-style:normal;font-size:10px;color:#278d70;background:#e8f8f1;border-radius:999px;padding:3px 7px}.ability-progress{height:6px;background:#e7eff0;border-radius:99px;overflow:hidden}.ability-progress span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--hx-teal),#4f91aa)}.ability-card p{height:50px;overflow:hidden;margin:11px 0 7px;color:#667c85;font-size:11px;line-height:1.5}.ability-source{display:block;text-align:right;color:#91a0aa;font-size:9px}
        .dimension-score{padding:22px;background:linear-gradient(145deg,#e8f8f6,#f9fcfc);border:1px solid #cce8e5;border-radius:16px}.dimension-score>small{display:block;color:#617b84}.dimension-score>b{font-size:55px;color:var(--hx-teal);line-height:1.05}.dimension-score>span{color:#93a5aa}.dimension-score>em{font-style:normal;margin-left:9px;padding:4px 9px;border-radius:999px;background:#def4ed;color:#218d6e;font-size:11px}.dimension-score>p{font-size:10px;color:#84979e;margin:7px 0 0}.sub-score{margin:14px 2px}.sub-score>span{font-size:11px;color:#5e747d}.sub-score>b{float:right;color:var(--hx-navy);font-size:11px}.sub-score>div{clear:both;height:6px;background:#e7eff0;border-radius:99px;overflow:hidden;margin-top:5px}.sub-score i{display:block;height:100%;background:linear-gradient(90deg,var(--hx-teal),#4f91aa);border-radius:99px}.sub-basis span{font-size:9px;color:#8b9da4}.sub-basis p{font-size:11px;color:#536c75;margin:3px 0;line-height:1.5}
        .evidence-hero{display:grid;grid-template-columns:1.2fr 2fr;gap:25px;align-items:center;padding:20px 22px;margin:7px 0 16px;background:linear-gradient(125deg,#eaf8f6,#f4f7ff);border:1px solid #cee5e5;border-radius:17px;position:relative}.evidence-hero div small{display:block;color:#6c858e}.evidence-hero div b{font-size:43px;color:var(--hx-teal)}.evidence-hero div span{margin-left:9px;padding:4px 9px;border-radius:999px;background:white;color:#58727d;font-size:10px}.evidence-hero p{margin:0;color:#58717a;font-size:12px;line-height:1.7}.evidence-hero p strong{display:block;color:var(--hx-navy);font-size:13px}.evidence-hero>em{position:absolute;right:18px;bottom:9px;font-style:normal;font-size:9px;color:#8da0aa}
        .source-label{color:var(--hx-navy);font-size:12px;font-weight:700;margin-bottom:8px}.source-quote{padding:15px 17px;border-radius:13px;background:#f7fafb;border-left:4px solid var(--hx-teal);font-size:12px;line-height:1.75;color:#506872}.ai-inference{padding:13px 15px;border-radius:13px;background:#edf9f7;border-left:4px solid var(--hx-teal)}.ai-inference p{margin:0;color:#50647a;font-size:12px;line-height:1.65}.ai-inference small{display:block;text-align:right;color:#7d9b99;font-size:9px;margin-top:8px}.trace-chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;align-items:center;gap:8px;margin:17px 0 4px;padding:14px;background:#f4f8f8;border-radius:14px}.trace-chain div{text-align:center}.trace-chain b{display:block;color:var(--hx-navy);font-size:11px}.trace-chain span{font-size:9px;color:#8b9da4}.trace-chain i{font-style:normal;color:var(--hx-teal)}
        .evidence-row{padding:12px 14px;margin:8px 0;border:1px solid #dce9eb;border-radius:12px;background:#fbfdfd}.evidence-row b{color:var(--hx-navy);font-size:12px}.evidence-row p{margin:5px 0 0;color:#687e87;font-size:12px;line-height:1.55}.risk-detail{padding:13px 15px;margin:9px 0;border-radius:12px;background:#fff8ee;border:1px solid #f1d4ad}.risk-detail b{color:#a65b20}.risk-detail p{font-size:12px;margin:5px 0;color:#7d634f}.risk-detail small{font-size:10px;color:#9a806b}
        [data-testid="stDataFrame"],[data-testid="stPlotlyChart"]{border-color:var(--hx-line)!important;box-shadow:none!important}.stButton>button[kind="primary"]{background:var(--hx-teal);border-color:var(--hx-teal)}
        @media(max-width:900px){.talent-page-head{align-items:flex-start;flex-direction:column}.talent-head-stats{width:100%;justify-content:space-between}.talent-head-stats>div{flex:1}.candidate-conclusion{grid-template-columns:1fr}.detail-kpis{grid-template-columns:repeat(2,1fr)}.detail-steps i{display:none}.evidence-hero{grid-template-columns:1fr}.trace-chain{grid-template-columns:1fr}.trace-chain i{transform:rotate(90deg)}[data-testid="stTabs"] [data-testid="stTab"]{padding:0 12px!important}}
        </style>
        """,
        unsafe_allow_html=True,
    )
