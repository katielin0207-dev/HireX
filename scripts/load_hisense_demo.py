"""Load Hisense demo JD and candidates into sessions/.

Run on Windows:
    .\\.venv\\Scripts\\python.exe scripts\\load_hisense_demo.py

Run on macOS:
    .venv/bin/python scripts/load_hisense_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "mock" / "hisense_demo"
SESSIONS = ROOT / "sessions"
CANDIDATES_DIR = SESSIONS / "candidates"


def read_text(name: str) -> str:
    return (DEMO / "resumes" / name).read_text(encoding="utf-8")


JD = json.loads((DEMO / "jd_现场工艺工程师.json").read_text(encoding="utf-8"))


CANDIDATES = [
    {
        "id": "hisense_001",
        "name": "林嘉豪",
        "resume_file": "mock/hisense_demo/resumes/01_林嘉豪_强匹配_现场工艺.txt",
        "resume_text": read_text("01_林嘉豪_强匹配_现场工艺.txt"),
        "resume_parsed": {
            "education": [{"school": "华南理工大学", "degree": "本科", "major": "机械设计制造及其自动化", "start": "2022.09", "end": "2026.06"}],
            "experience": [{"company": "某家电制造企业", "title": "工艺实习生", "start": "2025.07", "end": "2025.10"}],
            "skills": ["CAD", "SolidWorks", "Excel", "Minitab", "PFMEA", "SOP", "精益改善", "制造现场"],
            "total_years": 0.3,
        },
        "match_result": {
            "overall_score": 92,
            "hard_score": 94,
            "soft_score": 89,
            "recommendation": "推进",
            "breakdown": {
                "skills_match": {"score": 93, "reason": "覆盖工艺改善、质量分析、SOP、Excel、CAD 等核心要求"},
                "experience_match": {"score": 90, "reason": "有家电制造现场实习和冰箱装配改善项目"},
                "education_match": {"score": 95, "reason": "机械相关本科，2026届符合要求"},
                "project_relevance": {"score": 92, "reason": "冰箱抽屉装配效率优化项目与岗位高度相关"}
            },
            "matched_points": ["机械专业匹配", "有家电制造现场经验", "能接受一线和倒班", "有节拍和 SOP 改善案例"],
            "gap_points": ["正式工作经验不足，需要入职后导师带教"],
            "summary": "强匹配候选人，适合作为现场工艺工程师优先推进。"
        },
        "risk_report": {"level": "低", "risks": [], "interview_focus": ["追问冰箱门体发泡段改善中的个人贡献", "确认能接受生产一线节奏和阶段性倒班"]},
        "interview_eval": None,
        "status": "screened",
        "tags": ["海信容声", "现场工艺", "强匹配", "2026届"],
    },
    {
        "id": "hisense_002",
        "name": "陈雨桐",
        "resume_file": "mock/hisense_demo/resumes/02_陈雨桐_备选_IE改善.txt",
        "resume_text": read_text("02_陈雨桐_备选_IE改善.txt"),
        "resume_parsed": {
            "education": [{"school": "广东工业大学", "degree": "本科", "major": "工业工程", "start": "2022.09", "end": "2026.06"}],
            "experience": [{"company": "佛山某制造企业", "title": "IE实习生", "start": "2025.06", "end": "2025.09"}],
            "skills": ["Excel", "山积图", "ECRS", "5Why", "鱼骨图", "流程改善", "生产计划"],
            "total_years": 0.3,
        },
        "match_result": {
            "overall_score": 84,
            "hard_score": 86,
            "soft_score": 82,
            "recommendation": "待定",
            "breakdown": {
                "skills_match": {"score": 82, "reason": "IE 与效率改善能力较强，但工艺文件和制冷结构经验不足"},
                "experience_match": {"score": 83, "reason": "有制造现场 IE 实习，贴近产线改善"},
                "education_match": {"score": 92, "reason": "工业工程本科，2026届符合要求"},
                "project_relevance": {"score": 78, "reason": "线平衡项目相关，但非冰箱/制冷场景"}
            },
            "matched_points": ["IE 数据分析能力强", "熟悉产线节拍和瓶颈分析", "沟通主动"],
            "gap_points": ["制冷系统和冰箱结构理解不足", "工艺异常闭环经验偏少"],
            "summary": "适合作为备选，若岗位偏 IE 改善可优先考虑。"
        },
        "risk_report": {"level": "低", "risks": [], "interview_focus": ["验证其对冰箱制造流程的学习速度", "追问现场异常处理经验"]},
        "interview_eval": None,
        "status": "screened",
        "tags": ["海信容声", "IE", "备选", "2026届"],
    },
    {
        "id": "hisense_003",
        "name": "周明远",
        "resume_file": "mock/hisense_demo/resumes/03_周明远_高风险_经历断层.txt",
        "resume_text": read_text("03_周明远_高风险_经历断层.txt"),
        "resume_parsed": {
            "education": [{"school": "湖南工业大学", "degree": "本科", "major": "材料成型及控制工程", "start": "2018.09", "end": "2022.06"}],
            "experience": [
                {"company": "东莞某五金厂", "title": "工艺助理", "start": "2022.07", "end": "2023.03"},
                {"company": "佛山某自动化设备公司", "title": "工艺工程师", "start": "2025.06", "end": "至今"}
            ],
            "skills": ["CAD", "Excel", "冲压工艺", "PLC", "质量问题分析"],
            "total_years": 1.5,
        },
        "match_result": {
            "overall_score": 58,
            "hard_score": 62,
            "soft_score": 50,
            "recommendation": "不推进",
            "breakdown": {
                "skills_match": {"score": 60, "reason": "具备基础工艺经验，但冰箱制造和质量工具证据不足"},
                "experience_match": {"score": 45, "reason": "经历断层明显，且项目贡献缺少数据"},
                "education_match": {"score": 85, "reason": "材料成型本科相关"},
                "project_relevance": {"score": 48, "reason": "多为五金/设备文档整理，与冰箱现场工艺有差距"}
            },
            "matched_points": ["有制造现场接触", "专业背景部分相关"],
            "gap_points": ["2023.04-2025.05 经历断层", "PLC 熟练度缺少项目证据", "六西格玛证书过期"],
            "summary": "存在明显风险，建议先核验经历和证书，不建议直接推进。"
        },
        "risk_report": None,
        "interview_eval": None,
        "status": "screened",
        "tags": ["海信容声", "高风险", "经历断层", "证书过期"],
    },
    {
        "id": "hisense_004",
        "name": "何思琪",
        "resume_file": "mock/hisense_demo/resumes/04_何思琪_质量方向_可转岗.txt",
        "resume_text": read_text("04_何思琪_质量方向_可转岗.txt"),
        "resume_parsed": {
            "education": [{"school": "合肥工业大学", "degree": "本科", "major": "测控技术与仪器", "start": "2022.09", "end": "2026.06"}],
            "experience": [{"company": "某汽车零部件公司", "title": "质量实习生", "start": "2025.07", "end": "2025.09"}],
            "skills": ["Minitab", "Excel", "8D", "SPC", "检具管理", "质量巡检", "CAD"],
            "total_years": 0.2,
        },
        "match_result": {
            "overall_score": 78,
            "hard_score": 80,
            "soft_score": 76,
            "recommendation": "待定",
            "breakdown": {
                "skills_match": {"score": 78, "reason": "质量工具强，工艺改善能力需补充"},
                "experience_match": {"score": 76, "reason": "汽车零部件质量实习可迁移，但非冰箱制造"},
                "education_match": {"score": 88, "reason": "测控相关本科符合技术类基础"},
                "project_relevance": {"score": 70, "reason": "更适合现场质量工程师"}
            },
            "matched_points": ["质量分析工具较强", "有 8D 和 SPC 经验"],
            "gap_points": ["现场工艺文件和产线节拍改善经验不足"],
            "summary": "质量方向匹配较好，可作为质量岗位或工艺岗位备选。"
        },
        "risk_report": {"level": "低", "risks": [], "interview_focus": ["确认其是否愿意从质量岗转向工艺岗", "追问 8D 案例中的个人贡献"]},
        "interview_eval": None,
        "status": "screened",
        "tags": ["海信容声", "质量", "可转岗", "2026届"],
    },
    {
        "id": "hisense_005",
        "name": "邓启辰",
        "resume_file": "mock/hisense_demo/resumes/05_邓启辰_生产管理_一线意愿强.txt",
        "resume_text": read_text("05_邓启辰_生产管理_一线意愿强.txt"),
        "resume_parsed": {
            "education": [{"school": "武汉科技大学", "degree": "本科", "major": "机械工程", "start": "2022.09", "end": "2026.06"}],
            "experience": [{"company": "武汉某装备制造公司", "title": "生产实习生", "start": "2025.06", "end": "2025.08"}],
            "skills": ["Excel", "PPT", "CAD", "5S", "生产计划统计"],
            "total_years": 0.2,
        },
        "match_result": {
            "overall_score": 72,
            "hard_score": 70,
            "soft_score": 78,
            "recommendation": "待定",
            "breakdown": {
                "skills_match": {"score": 66, "reason": "工艺和质量工具不足"},
                "experience_match": {"score": 72, "reason": "有生产现场接触，技术深度不足"},
                "education_match": {"score": 88, "reason": "机械工程本科符合基础要求"},
                "project_relevance": {"score": 64, "reason": "更偏生产管理，不是工艺改善"}
            },
            "matched_points": ["一线意愿强", "执行和组织能力较好"],
            "gap_points": ["工艺分析工具不足", "缺少质量闭环案例"],
            "summary": "可作为生产管理方向候选人，工艺岗需谨慎。"
        },
        "risk_report": {"level": "低", "risks": [], "interview_focus": ["确认其长期一线发展意愿", "追问工艺分析和质量闭环方法"]},
        "interview_eval": None,
        "status": "screened",
        "tags": ["海信容声", "生产管理", "一线意愿强", "2026届"],
    },
    {
        "id": "hisense_006",
        "name": "罗子轩",
        "resume_file": "mock/hisense_demo/resumes/06_罗子轩_错配_软件后台.txt",
        "resume_text": read_text("06_罗子轩_错配_软件后台.txt"),
        "resume_parsed": {
            "education": [{"school": "深圳大学", "degree": "本科", "major": "软件工程", "start": "2022.09", "end": "2026.06"}],
            "experience": [{"company": "某互联网公司", "title": "后端开发实习生", "start": "2025.07", "end": "2025.10"}],
            "skills": ["Python", "FastAPI", "MySQL", "Redis", "Docker", "Git"],
            "total_years": 0.3,
        },
        "match_result": {
            "overall_score": 43,
            "hard_score": 38,
            "soft_score": 52,
            "recommendation": "不推进",
            "breakdown": {
                "skills_match": {"score": 30, "reason": "技能集中在软件后端，与现场工艺核心要求不匹配"},
                "experience_match": {"score": 35, "reason": "无制造现场、工艺改善或质量经验"},
                "education_match": {"score": 55, "reason": "本科符合，但专业不匹配"},
                "project_relevance": {"score": 25, "reason": "互联网项目与冰箱制造现场弱相关"}
            },
            "matched_points": ["数据和系统思维较好"],
            "gap_points": ["不接受长期倒班", "缺少制造现场经验", "专业与岗位要求错配"],
            "summary": "不适合现场工艺工程师，可转推荐软件/数字化相关岗位。"
        },
        "risk_report": {"level": "低", "risks": [], "interview_focus": ["确认是否愿意转向制造数字化岗位", "不建议按现场工艺岗推进"]},
        "interview_eval": None,
        "status": "screened",
        "tags": ["错配", "软件后台", "不推进"],
    },
]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    SESSIONS.mkdir(exist_ok=True)
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in CANDIDATES_DIR.glob("*.json"):
        old_file.unlink()
    write_json(SESSIONS / "jd.json", JD)
    print("loaded sessions/jd.json:", JD["title"])
    for candidate in CANDIDATES:
        write_json(CANDIDATES_DIR / f"{candidate['id']}.json", candidate)
        print("loaded", candidate["id"], candidate["name"])
    print("Hisense demo pack ready.")


if __name__ == "__main__":
    main()
