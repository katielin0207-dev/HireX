"""校准闭环效果验证：修订到底有没有让输出变好？

为什么需要这个脚本
------------------
`pipeline.py::_calibrate` 的逻辑闭环（校验 → 反馈 → 修订 → 再校验 → 择优）
是验证过的，但「修订 prompt 到底有没有让输出变好」此前只有一条 75→87→80
的轨迹 —— 三个点里最后一轮反而更差，样本太少，无法判断是噪声还是趋势。

本脚本重复跑 N 次真实分析，把每条校准链的**逐轮加权分**打出来，回答三件事：

  1. 修订后的分数是升还是降（改好了还是改坏了）
  2. 「择优」是否真的必要（最后一轮 == 最高分轮的比例）
  3. 首轮即 PASS 的比例（PASS 不进修订，这类样本要排除在效果评估外）

实现说明：CheckerResult 上没有 output_type 字段，所以两条链无法从结果反推。
这里包装 `_calibrate` 来记录，而不是猜 —— 包装的是真实生产路径本身，
不复制它的逻辑，避免"验证脚本和被验证对象各跑一套"。

用法
----
    .venv\\Scripts\\python.exe scripts\\verify_calibration.py [轮数]

默认 3 轮。每轮是一次完整分析（实测约 155s），**真实消耗 LLM 额度**。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline import RecruitmentPipeline  # noqa: E402
from app.llm_client import llm_client  # noqa: E402

JD_TEXT = """
后端开发工程师（Python）
职责：负责 AI 应用后端服务开发，设计并实现高并发 API；参与 LLM 应用架构设计。
要求：
1. 熟练 Python，熟悉 FastAPI / Flask 之一
2. 熟悉 PostgreSQL / Redis，理解索引与事务
3. 有 LLM 应用开发经验（RAG、Agent、微调任一）
4. 本科及以上，计算机相关专业
加分：Docker/K8s、开源贡献、分布式系统经验
"""


def run_once(resume_text: str, idx: int) -> dict:
    """跑一次完整分析，返回每条校准链的逐轮分。"""
    captured: dict[str, dict] = {}
    original = RecruitmentPipeline._calibrate

    def wrapped(self, initial_output, regenerate, source, output_type):
        out, history = original(self, initial_output, regenerate, source, output_type)
        captured[output_type] = {
            # weighted_score 由 checker 自己填（checker.py:242），与 pipeline
            # 择优用的 _weighted_score 同口径，直接取即可，不重算
            "scores": [round(h.weighted_score, 1) for h in history],
            "passes": [h.overall_pass for h in history],
            "skipped": history[0].skipped_dimensions if history else [],
        }
        return out, history

    RecruitmentPipeline._calibrate = wrapped
    try:
        p = RecruitmentPipeline(llm_client=llm_client)
        p.setup(jd_text=JD_TEXT, resume_text=resume_text)
        t0 = time.time()
        p.run()
        dur = time.time() - t0
    finally:
        RecruitmentPipeline._calibrate = original

    print(f"\n--- 第 {idx} 次  ({dur:.0f}s) ---")

    # 修订失败/空返回会让某条链只留 1 轮记录却标"未过"，光看分数看不出原因，
    # 所以把 execution_log 里的对应事件一并打出来
    for ev in p.execution_log:
        if ev.get("event") in ("revision_failed", "revision_empty", "calibration_degraded"):
            print(f"  [log] {ev}")

    out = {"duration": dur, "chains": {}, "events": [
        ev for ev in p.execution_log
        if ev.get("event") in ("revision_failed", "revision_empty")
    ]}
    for name, rec in captured.items():
        scores, passes = rec["scores"], rec["passes"]
        if not scores:
            continue
        best_i = scores.index(max(scores))
        info = {
            "scores": scores,
            "passed_at": (passes.index(True) + 1) if any(passes) else None,
            "best_round": best_i + 1,
            "last_is_best": best_i == len(scores) - 1,
            "improved": len(scores) > 1 and scores[-1] > scores[0],
            "skipped": rec["skipped"],
        }
        out["chains"][name] = info
        tag = f"第{info['passed_at']}轮PASS" if info["passed_at"] else "三轮未过"
        skip = f"  跳过维度:{','.join(rec['skipped'])}" if rec["skipped"] else ""
        print(f"  {name:18s} 逐轮分 {scores}  最高第{info['best_round']}轮  {tag}{skip}")
    return out


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    sample = ROOT / "test_resumes" / "示例简历-王思远-后端开发.txt"
    resume_text = sample.read_text(encoding="utf-8")

    print(f"校准闭环验证：{n} 次真实分析（消耗 LLM 额度）")
    print(f"简历：{sample.name}   JD：后端开发工程师（Python）")

    runs = []
    for i in range(n):
        try:
            runs.append(run_once(resume_text, i + 1))
        except Exception as e:  # noqa: BLE001
            print(f"  第 {i+1} 次失败：{type(e).__name__}: {e}")

    if not runs:
        print("\n全部失败，无法评估。")
        return

    print("\n" + "=" * 66)
    print("汇总")
    print("=" * 66)
    per_chain: dict[str, list] = {}
    for r in runs:
        for name, rec in r["chains"].items():
            per_chain.setdefault(name, []).append(rec)

    for name, recs in per_chain.items():
        multi = [r for r in recs if len(r["scores"]) > 1]      # 进过修订的样本
        first_pass = sum(1 for r in recs if r["passed_at"] == 1)
        print(f"\n{name}")
        print(f"  样本 {len(recs)}   首轮即 PASS {first_pass}   进入修订 {len(multi)}")
        if not multi:
            print("  → 从未进入修订：首轮就过了，本链评估不了修订效果（这本身是好结果）")
            continue
        improved = sum(1 for r in multi if r["improved"])
        last_best = sum(1 for r in multi if r["last_is_best"])
        print(f"  修订后分数上升          {improved}/{len(multi)}")
        print(f"  最后一轮恰好是最高分     {last_best}/{len(multi)}")
        if last_best < len(multi):
            print("  → 存在「最后一轮不是最好」的样本，**择优是必要的**")
        else:
            print("  → 本批样本里最后一轮都恰好最好，择优没起作用（但不代表可以去掉）")
        for r in multi:
            print(f"    {r['scores']}  最高第{r['best_round']}轮")

    print("\n判读：")
    print("  · 修订后分数上升占多数 → 修订 prompt 方向正确")
    print("  · 最后一轮恰好最高分不足 100% → 不能返回最后一轮，择优必须保留")
    print("  · 某条链总是首轮 PASS → 该链维度判定已够宽松，修订链路用不上")


if __name__ == "__main__":
    main()
