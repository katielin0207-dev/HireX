# HireX 招聘 AI — Claude Code 项目上下文

> 本文件会被 Claude Code 自动加载为项目记忆。完整背景先读 `HANDOFF.md`；逐小时执行计划读 `docs/PLAYBOOK_3人执行手册.md`。

## 一句话
国内企业全流程招聘 AI（HR + 用人部门），24 小时 MVP，基于 `luke99810/AI-recruitment-system` 二次开发，Streamlit 前端。3 人协作：**A=基建+简历筛选+合并（已完成），B=风险识别+面试辅助（未开工），C=人才评价+联调（未开工）**。

## 先读这几个文件（按顺序）
1. `HANDOFF.md` — 完整交接上下文（技术决策、已知坑、待办）
2. `docs/CONTRACT.md` — 候选人 JSON 契约。**模块间禁止互相 import，只读写 `sessions/candidates/{id}.json`**
3. `app/views/screening.py` — A 的参考实现（JD编辑→批量导入→规则+LLM评分→排名→审核）
4. `app/shared/` — `llm.py`(call_llm 封装 DeepSeek) `store.py`(JSON原子读写) `parallel.py`(map_llm并发) `demo_cache.py`

## 硬性约束（不要回退）
- **只用国产模型**：DeepSeek，经 `app/shared/llm.py` 的 `call_llm`。禁止引入 GPT/Claude API。
- **硬性条件走规则引擎**：学历/年限/技能等硬门槛用确定性规则打分，不走 LLM（POC 实测 LLM 学历分波动 ±15）。不满足硬门槛 = 0 分 + "不推进"否决。
- **轻量管线**：每个新模块只做 1 次 LLM 调用。别抄基座 20 分钟的重型 pipeline。
- **只有 A 能改 `app/main.py`**（导航注册）。新模块写 `app/views/<模块名>.py`，由 A 在合并点注册导航。
- **pandas ≥ 2.1**：用 `df.style.map(...)`，不要用已删除的 `applymap`。

## 运行
```bash
source .venv/bin/activate
streamlit run app/main.py --server.port 8501   # 或 ./dev.sh（./dev.sh demo = 演示缓存模式）
```
- DeepSeek API key 在项目根目录 `.env`（**不进 git**，向 Katie 索取完整值）。
- 前端正在 `http://127.0.0.1:8501` 运行。

## 已知坑（别再踩）
- Streamlit 长任务 WebSocket 会冻住 → 用轻量管线或 `./dev.sh demo` 缓存兜底。
- `app/ui/theme.py` 全局 `p/li/span/label` 着色会盖掉 Streamlit 控件内部文字（紫底按钮/多选标签文字看不见）→ 需给后代元素显式白字覆盖，主按钮和 multiselect 已修。
- uvloop 与 nest_asyncio 冲突 → `pip uninstall uvloop`。
- 推 GitHub 偶发 502 → 重试即可（不要 unset proxy，直连不通）。

## 下一步
按 `docs/PLAYBOOK_3人执行手册.md`：B 写风险识别+面试辅助，C 写人才评价，第 6/10/14 小时由 A 三次合并进 main。
