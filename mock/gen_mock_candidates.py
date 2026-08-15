"""生成 Mock JD 和 3 个候选人 JSON 示例（展示契约字段的标准填法）。

运行：python mock/gen_mock_candidates.py
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

JD = {
    "title": "Python 后端开发工程师",
    "raw_text": """Python 后端开发工程师

【岗位职责】
1. 负责公司核心业务系统的后端开发与维护，参与系统架构设计
2. 负责微服务的设计、开发和优化，保障系统高可用和高性能
3. 参与数据库设计和优化，编写高效 SQL 及缓存策略
4. 参与代码评审，指导初中级工程师，推动团队技术成长
5. 跟进新技术趋势，评估并引入适合团队的技术方案

【任职要求】
1. 本科及以上学历，计算机相关专业优先
2. 3年以上 Python 后端开发经验，熟悉 FastAPI 或 Django 框架
3. 熟悉 MySQL、Redis 等常用存储，有数据库优化经验
4. 熟悉微服务架构，有服务拆分和治理经验
5. 熟悉 Docker、Git、CI/CD 等工程化工具
6. 具备良好的编码习惯和文档习惯

【加分项】
1. 有 Elasticsearch 使用经验
2. 有 LLM/AI 应用开发经验（RAG、Prompt 工程等）
3. 有高并发场景经验（大促、秒杀等）
4. 有开源项目贡献经验
5. 了解 Go 语言

【薪资范围】15-25K·14薪
【工作地点】上海""",
    "requirements": {
        "hard": {
            "degree": "本科",
            "min_years": 3,
            "must_skills": ["Python", "FastAPI", "Django", "MySQL", "Redis", "Docker", "Git"],
            "nice_skills": ["Elasticsearch", "Go", "Kubernetes", "LLM", "RAG"],
        },
        "soft": ["沟通协作", "学习能力", "抗压能力", "代码评审与指导能力"],
    },
}

# 3 个候选人示例：优秀 / 中等 / 风险，字段填法即标准
CANDIDATES = [
    {
        "id": "cand_001",
        "name": "陈晓",
        "resume_file": "mock/resumes/01_陈晓_优秀.txt",
        "resume_text": "（由 B 在上传/导入时填充完整原文，此处省略）",
        "resume_parsed": {
            "education": [
                {"school": "上海交通大学", "degree": "硕士", "major": "计算机科学与技术", "start": "2019.09", "end": "2022.06"},
                {"school": "上海交通大学", "degree": "本科", "major": "计算机科学与技术", "start": "2015.09", "end": "2019.06"},
            ],
            "experience": [
                {"company": "拼多多", "title": "高级后端开发工程师", "start": "2022.07", "end": "至今"},
                {"company": "字节跳动", "title": "后端开发实习生", "start": "2020.03", "end": "2022.06"},
            ],
            "skills": ["Python", "Go", "FastAPI", "Django", "Celery", "MySQL", "Redis", "Elasticsearch", "ChromaDB", "Kafka", "Docker", "Kubernetes"],
            "total_years": 3.1,
        },
        "match_result": {
            "overall_score": 91,
            "hard_score": 95,
            "soft_score": 86,
            "recommendation": "推进",
            "breakdown": {
                "skills_match": {"score": 95, "reason": "必备技能全覆盖，加分项命中 ES/K8s/RAG/Go 四项"},
                "experience_match": {"score": 92, "reason": "3.1 年大厂后端经验，日均 2 亿次请求的高并发实战"},
                "education_match": {"score": 100, "reason": "上海交大硕士，计算机科班"},
                "project_relevance": {"score": 88, "reason": "RAG 质检系统直接命中 LLM 加分项"},
            },
            "matched_points": ["技能全覆盖且深度足够", "大厂高并发经验", "硕士学历", "有带人和代码评审经验"],
            "gap_points": ["硕士应届起步，独立带团队经验有限"],
            "summary": "高匹配候选人，技能、经验、学历全面达标，建议优先推进。",
        },
        "risk_report": {
            "level": "低",
            "risks": [],
            "interview_focus": ["核实优惠券系统改造中的个人具体贡献", "了解其带 2 名初级工程师的管理方式"],
        },
        "interview_eval": None,
        "status": "risk_checked",
        "tags": ["Python", "3年经验", "大厂", "RAG", "高并发"],
        "updated_at": "2026-08-15T10:00:00",
    },
    {
        "id": "cand_002",
        "name": "孙强",
        "resume_file": "mock/resumes/04_孙强_中等.txt",
        "resume_text": "（由 B 在上传/导入时填充完整原文，此处省略）",
        "resume_parsed": {
            "education": [{"school": "华中科技大学", "degree": "本科", "major": "软件工程", "start": "2018.09", "end": "2022.06"}],
            "experience": [{"company": "武汉某软件公司", "title": "Python 开发工程师", "start": "2022.07", "end": "至今"}],
            "skills": ["Python", "Django", "FastAPI", "Celery", "MySQL", "Redis", "Docker", "Git"],
            "total_years": 3.1,
        },
        "match_result": {
            "overall_score": 68,
            "hard_score": 78,
            "soft_score": 55,
            "recommendation": "待定",
            "breakdown": {
                "skills_match": {"score": 75, "reason": "必备技能基本覆盖，但无 ES/K8s 等加分项"},
                "experience_match": {"score": 62, "reason": "年限达标但为单体应用经验，无微服务和高并发实战"},
                "education_match": {"score": 100, "reason": "华科本科，符合要求"},
                "project_relevance": {"score": 55, "reason": "项目为内部 OA/报表，与 JD 核心系统关联度低"},
            },
            "matched_points": ["年限达标", "学历符合", "基础技能齐全"],
            "gap_points": ["无微服务经验", "无高并发场景", "公司背景一般"],
            "summary": "基本素质达标但实战经验与 JD 要求有差距，建议作为备选。",
        },
        "risk_report": {
            "level": "低",
            "risks": [{"type": "技能存疑", "severity": "low", "detail": "FastAPI 自评'熟悉'但项目均为 Django", "evidence": "框架：Django（熟练）、FastAPI（熟悉）"}],
            "interview_focus": ["验证 FastAPI 实际使用深度", "考察微服务架构理解"],
        },
        "interview_eval": None,
        "status": "screened",
        "tags": ["Python", "3年经验", "单体应用"],
        "updated_at": "2026-08-15T10:05:00",
    },
    {
        "id": "cand_003",
        "name": "马跃",
        "resume_file": "mock/resumes/08_马跃_风险_经历断层.txt",
        "resume_text": "（由 B 在上传/导入时填充完整原文，此处省略）",
        "resume_parsed": {
            "education": [{"school": "东华大学", "degree": "本科", "major": "软件工程", "start": "2014.09", "end": "2018.06"}],
            "experience": [
                {"company": "上海某科技公司", "title": "后端开发工程师", "start": "2024.06", "end": "至今"},
                {"company": "某外包公司", "title": "Python 开发工程师", "start": "2020.03", "end": "2021.12"},
            ],
            "skills": ["Python", "Django", "FastAPI", "MySQL", "Redis", "Git", "Docker"],
            "total_years": 3.5,
        },
        "match_result": {
            "overall_score": 52,
            "hard_score": 60,
            "soft_score": 42,
            "recommendation": "不推进",
            "breakdown": {
                "skills_match": {"score": 62, "reason": "技能覆盖基础项但深度不足"},
                "experience_match": {"score": 45, "reason": "自称 6 年经验但可核实仅 3.5 年，存在 2.4 年空档"},
                "education_match": {"score": 100, "reason": "本科达标"},
                "project_relevance": {"score": 40, "reason": "项目为内部小工具，复杂度低"},
            },
            "matched_points": ["学历达标", "基础技能具备"],
            "gap_points": ["经历断层 2.4 年无法解释", "经验年限自述与可核实不符", "项目复杂度低"],
            "summary": "存在重大经历断层风险，建议谨慎。",
        },
        "risk_report": {
            "level": "高",
            "risks": [
                {"type": "经历断层", "severity": "high",
                 "detail": "2022.01-2024.05 共 2 年 4 个月无工作经历，简历未说明",
                 "evidence": "2020.03-2021.12 某外包公司 → 2024.06 至今，中间无记录"},
                {"type": "信息存疑", "severity": "medium",
                 "detail": "自述 6 年经验，可核实仅 3.5 年",
                 "evidence": "语言：Python（熟练，自称6年）"},
                {"type": "信息存疑", "severity": "medium",
                 "detail": "空档期自称'自由职业'但无项目证明",
                 "evidence": "面试中解释为'自由职业'，但无法提供项目证明"},
            ],
            "interview_focus": ["必须核实 2022-2024 空档期真实去向", "要求提供空档期收入/社保证明", "技术深度验证（疑似包装）"],
        },
        "interview_eval": None,
        "status": "risk_checked",
        "tags": ["Python", "经历断层", "高风险"],
        "updated_at": "2026-08-15T10:10:00",
    },
]


def main():
    sessions = os.path.join(ROOT, "sessions")
    cands_dir = os.path.join(sessions, "candidates")
    os.makedirs(cands_dir, exist_ok=True)

    with open(os.path.join(sessions, "jd.json"), "w", encoding="utf-8") as f:
        json.dump(JD, f, ensure_ascii=False, indent=2)
    print("  ✓ sessions/jd.json")

    for cand in CANDIDATES:
        path = os.path.join(cands_dir, f"{cand['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cand, f, ensure_ascii=False, indent=2)
        print(f"  ✓ sessions/candidates/{cand['id']}.json ({cand['name']})")

    print(f"\nMock 数据生成完成")


if __name__ == "__main__":
    main()
