"""A 模块端到端验证脚本（无界面）：验证筛选链路可用后自动清理测试数据。"""
import sys, os, json, shutil, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.views import screening as M
from app.shared import save_jd, save_candidate, list_candidates, load_candidate

RESUMES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mock", "resumes")
TEST_IDS = []

JD_TEXT = """招聘 Python 后端开发工程师
【任职要求】本科及以上，3年以上 Python 后端经验，熟悉 FastAPI/Django，熟悉 MySQL/Redis，
有微服务经验优先。软实力：沟通协作、学习能力、抗压能力。"""

print("=== 1. 硬性规则引擎单测（确定性）===")
req_hard = {"degree": "本科", "min_years": 3, "must_skills": ["Python", "FastAPI", "MySQL", "Redis"]}
# 完全匹配
parsed_full = {"education": [{"degree": "本科"}], "total_years": 4.0, "skills": ["Python", "FastAPI", "MySQL", "Redis", "K8s"]}
d, y, sk, det = M.hard_rule_engine(req_hard, parsed_full)
print(f"  全匹配 -> 学历{d} 年限{y} 技能{sk} | 缺失:{det['missing']}")
assert (d, y, sk) == (100, 100, 100), "全匹配应满分"
# 年限不足
parsed_low = {"education": [{"degree": "本科"}], "total_years": 2.0, "skills": ["Python", "FastAPI"]}
d2, y2, sk2, det2 = M.hard_rule_engine(req_hard, parsed_low)
print(f"  年限不足 -> 学历{d2} 年限{y2} 技能{sk2} | 缺失:{det2['missing']}")
assert d2 == 100 and 0 < y2 < 100 and sk2 == 50, "年限不足应降分，技能命中2/4=50"
# 学历不足
parsed_deg = {"education": [{"degree": "大专"}], "total_years": 5.0, "skills": ["Python", "FastAPI", "MySQL", "Redis"]}
d3, y3, sk3, det3 = M.hard_rule_engine(req_hard, parsed_deg)
print(f"  学历不足 -> 学历{d3} 年限{y3} 技能{sk3}")
assert d3 == 0, "大专不满足本科应0分"
# 确定性：同输入跑两次结果一致
r1 = M.hard_rule_engine(req_hard, parsed_full)
r2 = M.hard_rule_engine(req_hard, parsed_full)
assert r1 == r2, "规则引擎必须确定性（POC 核心教训）"
print("  ✓ 确定性通过（消除学历分波动问题）")

print("\n=== 2. JD 结构化 ===")
jd_req = M.parse_jd(JD_TEXT)
save_jd({"title": jd_req.get("title", "岗位"), "raw_text": JD_TEXT,
         "requirements": jd_req, "weights": {"hard": 0.6, "soft": 0.4}})
print(f"  title={jd_req.get('title')} degree={jd_req['hard'].get('degree')} min_years={jd_req['hard'].get('min_years')}")

print("\n=== 3. 导入 2 份简历并解析 ===")
for fname in ["01_陈晓_优秀.txt", "08_马跃_风险_经历断层.txt"]:
    with open(os.path.join(RESUMES, fname), encoding="utf-8") as f:
        txt = f.read()
    parsed = M.parse_resume(txt)
    name = parsed.get("name") or M._infer_name(fname)
    cid = "test_" + re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", name)[:8]
    cand = {"id": cid, "name": name, "resume_text": txt,
            "resume_file": os.path.join("mock", "resumes", fname),
            "resume_parsed": parsed, "status": "new", "tags": parsed.get("skills", [])}
    save_candidate(cand)
    TEST_IDS.append(cid)
    print(f"  {name}: 学历={[e.get('degree') for e in parsed.get('education',[])]} 年限={parsed.get('total_years')} 技能数={len(parsed.get('skills',[]))}")

print("\n=== 4. 批量筛选（硬性规则 + 软性 LLM）===")
from app.shared import load_jd
jd = load_jd()
n = M.run_screening(jd, 0.6, 0.4)
print(f"  已筛选 {n} 人")

print("\n=== 5. 筛选结果 ===")
for cid in TEST_IDS:
    c = load_candidate(cid)
    mr = c["match_result"]
    print(f"  {c['name']}: 硬性{mr['hard_score']} 软性{mr['soft_score']} 总分{mr['overall_score']} 推荐={mr['recommendation']}")
    print(f"    总结: {mr.get('summary','')[:80]}")
    if mr['gap_points']:
        print(f"    差距: {mr['gap_points'][0][:60]}")

print("\n=== 清理测试数据 ===")
base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessions", "candidates")
for cid in TEST_IDS:
    p = os.path.join(base, cid + ".json")
    if os.path.exists(p):
        os.remove(p)
print("  ✓ 已删除测试候选人，保留 mock 示例数据")

print("\n全部通过 ✓")
