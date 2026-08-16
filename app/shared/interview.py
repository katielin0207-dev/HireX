"""面试例题生成器（移植自「海信动态题库自动化工具」的题库数据）。

思路：原工具是 JS 静态引擎（题库 + 疑点模板 + 评分锚点）。本模块把题库
`mock/hisense-question-bank.json` 作为 LLM 的风格参考（追问方式 / 5-3-1
评分锚点 / 红旗信号 / 疑点转题模板），由 LLM 结合【岗位 JD + 候选人简历 +
匹配疑点】动态生成 6 道结构化面试题，输出契约与原工具 demo-output.json 一致：

  {"questions": [{"pool": "doubt|role|common|closing",
                  "competency": "...", "question": "...",
                  "followUps": [...], "anchors": {"5":..., "3":..., "1":...},
                  "redFlags": [...], "expectedMinutes": 5}]}
"""
import json
import os

from .llm import call_llm

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BANK_PATH = os.path.join(_ROOT, "mock", "hisense-question-bank.json")

SYSTEM_INTERVIEW = (
    "你是资深技术面试官，擅长根据岗位 JD 与候选人简历设计结构化面试题，"
    "并为每题给出追问、5/3/1 评分锚点与红旗信号。只输出 JSON。"
)


def load_question_bank() -> dict:
    """加载题库；文件缺失时返回空结构（生成器退化为纯 LLM 出题）。"""
    if not os.path.exists(_BANK_PATH):
        return {"questions": [], "doubtTemplates": {}}
    with open(_BANK_PATH, encoding="utf-8") as f:
        return json.load(f)


def _pick_references(bank: dict, max_role: int = 2) -> str:
    """从题库挑少量样例作为风格参考注入 prompt（控制 prompt 长度）。"""
    qs = bank.get("questions", [])
    role = [q for q in qs if q.get("pool") == "role"][:max_role]
    common = [q for q in qs if q.get("pool") == "common"][:1]
    refs = []
    for q in role + common:
        refs.append(
            f"- 【{q.get('competency', '')}】{q.get('question', '')}\n"
            f"  追问示例：{'；'.join(q.get('followUps', [])[:2])}\n"
            f"  锚点示例：5分={q.get('anchors', {}).get('5', '')[:60]}"
        )
    dts = bank.get("doubtTemplates", {})
    if dts:
        key = next(iter(dts))
        dt = dts[key]
        refs.append(
            f"- 【疑点转题模板·{dt.get('competency', '')}】{dt.get('question', '')}\n"
            f"  追问示例：{'；'.join(dt.get('followUps', [])[:2])}"
        )
    return "\n".join(refs) or "（无参考题，直接按面试官经验出题）"


def generate_interview_questions(job: dict, candidate: dict,
                                 match: dict, count: int = 4) -> dict:
    """根据岗位 + 候选人 + 匹配结果生成面试题。

    job:       岗位定义（haixin_jobs.json 的一条）
    candidate: 候选人记录（含 resume_parsed / resume_text）
    match:     该岗位的 match_result（summary / matched_points / gap_points）
    返回 {"questions": [...]}；LLM 不可用时自动使用岗位与疑点模板。
    """
    bank = load_question_bank()
    hard = job.get("hard", {})
    parsed = candidate.get("resume_parsed", {}) or {}
    gaps = match.get("gap_points", []) or []
    matched = match.get("matched_points", []) or []

    prompt = f"""请为以下岗位与候选人生成 {count} 道结构化面试题。

【岗位】{job.get('title', '')} · {job.get('dept', '')} · {job.get('level', '')}
【硬性要求】学历 {hard.get('degree', '不限')} · 年限 ≥{hard.get('min_years', 0)} 年 · 必备技能 {'、'.join(hard.get('must_skills', [])) or '无'}
【软性要求】{'、'.join(job.get('soft', [])) or '无'}
【JD 摘要】{(job.get('jd_text', '') or '')[:400]}

【候选人】{candidate.get('name', '')}
【简历要点】{json.dumps(parsed, ensure_ascii=False)[:800]}
【AI 匹配评价】{match.get('summary', '')}
【匹配点】{'；'.join(matched[:3]) or '无'}
【疑点 / 差距】{'；'.join(gaps[:3]) or '无'}

【题库风格参考】（学习其追问方式与评分锚点写法，不要照抄题目）
{_pick_references(bank)}

出题要求（简洁精炼、控制输出体量）：
1. 共 {count} 题，按面试顺序：疑点核查（doubt，1 题；如无疑点则出经历深挖题）
   → 专业技术（role，围绕必备技能，1-2 题）→ 软实力或收尾（common/closing，1 题）。
2. 疑点题必须引用简历中的具体说法或缺失点。
3. 每题输出：**追问 1 条**、**5/3/1 三档锚点各 ≤ 25 字**、**红旗信号 1 条**、预计分钟数。
4. 语言精炼，不要展开长段落，每字段紧扣要点即可。

严格输出 JSON（不要输出任何其他文字）：
{{
  "questions": [
    {{
      "pool": "doubt|role|common|closing",
      "competency": "考察能力点",
      "question": "题目",
      "followUps": ["追问1"],
      "anchors": {{"5": "优秀表现", "3": "合格表现", "1": "不合格表现"}},
      "redFlags": ["红旗1"],
      "expectedMinutes": 5
    }}
  ]
}}"""
    try:
        return call_llm(prompt, system=SYSTEM_INTERVIEW, expect_json=True)
    except Exception:
        skills = hard.get("must_skills", []) or ["岗位核心技能"]
        templates = []
        for gap in (gaps or ["简历中的关键经历缺少量化结果"]):
            templates.append(("doubt", "经历核验", f"请结合具体项目说明“{gap}”这一点，并提供可核验的过程与结果。"))
        for skill in skills:
            templates.append(("role", "专业能力", f"请介绍一次你实际运用 {skill} 解决业务问题的案例，你承担了什么责任？"))
        templates.extend([
            ("common", "协作与推动", "请举例说明一次跨部门意见不一致时，你如何推动问题闭环。"),
            ("closing", "求职动机", f"你为什么选择应聘{job.get('title', '该岗位')}，入职后三个月希望完成什么？"),
        ])
        questions = []
        for pool, competency, question in templates[:count]:
            questions.append({
                "pool": pool,
                "competency": competency,
                "question": question,
                "followUps": ["请说明当时的目标、个人动作和量化结果。", "如果重新处理，你会调整什么？"],
                "anchors": {
                    "5": "案例真实完整，个人贡献清晰，结果可量化并能复盘。",
                    "3": "有相关案例，过程基本清楚，但结果或个人贡献不够具体。",
                    "1": "无法提供实例，回答前后矛盾或明显回避关键细节。",
                },
                "redFlags": ["只描述团队成果，无法说明个人贡献", "无法提供时间、数据或具体产出"],
                "expectedMinutes": 5,
            })
        while len(questions) < count:
            questions.append(dict(questions[-1]))
        return {"questions": questions}
