# HANDOFF.md — 项目交接说明（给下一位 AI 的上下文包）

> 写给下一位迭代此项目的 AI：请先完整读完本文，再读代码。代码在 GitHub 仓库里，决策和背景在这里。

## 1. 项目一句话
为**国内企业**做的全流程招聘 AI Agent（HR + 用人部门），基于开源项目 `luke99810/AI-recruitment-system` 二次开发，**24 小时 MVP**、**3 人协作**。四大模块：简历筛选、风险识别、面试辅助、人才评价汇总。

## 2. 当前状态（2026-08-14 晚）
- **A（基建 + 简历筛选）已完成并推送**：`app/views/screening.py` 可跑，main 分支最新提交 `94d5edc`。
- **B（风险识别 + 面试辅助）、C（人才评价 + 联调）尚未开工**。
- 基座冗余已清理：34MB 演示视频从 git 历史删除、`test_resumes/` 删除、基座导航页（analysis/interview/report/skills）已隐藏。
- 前端 Streamlit 正在本地 `http://127.0.0.1:8501` 运行。

## 3. 核心技术决策（必须遵守，别回退）
1. **只用国产模型**：DeepSeek-V3 为主，不要引入 GPT/Claude。
2. **MVP 最大复用 Streamlit 基座**，生产环境后期才重构成 FastAPI + Vue + Celery。
3. **硬性条件走规则引擎，不走 LLM**：学历/年限/技能等硬门槛用确定性规则打分，消除 LLM 分数波动（POC 发现同一简历学历分波动 ±15）。
4. **轻量管线**：每个新模块只做 1 次 LLM 调用，不要抄基座 20 分钟的重型 pipeline。
5. **模块间不互相 import**：通过 `sessions/candidates/{id}.json` 读写统一 JSON 契约，契约见 `docs/CONTRACT.md`。
6. **只有 A 能改 `app/main.py`**：B/C 开发自己的 view 文件，导航入口由 A 在合并点统一注册。

## 4. 代码地图（按这个顺序读）
| 优先级 | 文件/目录 | 说明 |
|--------|-----------|------|
| 1 | `docs/PLAYBOOK_3人执行手册.md` | 逐小时执行计划、3 次合并点、砍单顺序 |
| 2 | `docs/CONTRACT.md` | 候选人 JSON Schema、字段责任矩阵、状态枚举 |
| 3 | `app/views/screening.py` | A 的参考实现：JD 编辑 → 批量导入 → 规则+LLM 评分 → 排名 → 审核 |
| 4 | `app/shared/` | `llm.py`（DeepSeek 薄封装）、`store.py`（JSON 原子读写）、`parallel.py`（并发限流）、`demo_cache.py` |
| 5 | `mock/` | 10 份测试简历 + 3 个候选人 JSON 示例 |
| 6 | `app/main.py` | 入口、导航注册、主题注入 |
| 7 | `app/ui/theme.py` | 全局样式（注意全局 span 规则会覆盖控件文字） |

**不用读的基座旧代码**：`app/views/analysis.py`、`interview.py`、`report.py`、`skills_admin.py`（已隐藏，仅作备份参考）。

## 5. 运行方式
```bash
cd AI-recruitment-system
source .venv/bin/activate   # 虚拟环境已存在
streamlit run app/main.py --server.port 8501
# 或 ./dev.sh          # 正常模式
# 或 ./dev.sh demo     # 演示缓存模式（断网/API 故障时兜底）
```
- DeepSeek API key 放在项目根目录 `.env`（**不进 git**）。
- 若 clone 后没 `.env`，向 Katie 索取：`sk-350f...`（完整 key 私发）。

## 6. 已知坑（别再踩）
- **pandas ≥2.1**：`df.style.applymap` 已删除，必须用 `df.style.map`（已修，见 `30fdf73`）。
- **Streamlit 长任务 WebSocket 会冻住**：不要跑 20 分钟级 pipeline；用轻量管线或演示缓存。
- **主题 CSS 全局覆盖**：`p, li, span, label` 统一着色会盖掉按钮/多选标签内部文字，导致"紫底看不见字"。遇到先检查 `theme.py` 是否漏了后代覆盖（主按钮、multiselect 已修）。
- **git clone 曾 OOM**：34MB 视频已从历史删除，现在仓库仅 1MB；若队友仍用旧哈希，需 `git fetch && git reset --hard origin/main` 或重新 clone。
- **uvloop 与 nest_asyncio 冲突**：若报错，执行 `pip uninstall uvloop`。
- **代理不稳定**：推 GitHub 偶发 502，重试即可；不要 unset proxy（直连不通）。

## 7. 下一步待办（优先级）
1. B：风险识别模块（候选人 JSON 补 `risk_report` 字段，契约已留位）。
2. B：面试辅助模块（结构化题库、转写、评估表）。
3. C：人才评价模块（对比表、人才池、offer-fallback）。
4. 三次合并：第 6 / 10 / 14 小时，A 负责把 B/C 分支合并进 main 并注册导航。
5. 第 11–14 小时：预跑演示缓存 `./dev.sh`，确保 demo 断网可播。

## 8. GitHub 访问方式（二选一）
- **方式 A（推荐）**：让 Katie 把你的 GitHub 账号加为仓库 `katielin0207-dev/HireX` 的 Collaborator，然后 `git clone https://github.com/katielin0207-dev/HireX.git`。
- **方式 B（无 GitHub）**：Katie 把仓库打包/上传到你们的工作环境；`.env` 单独私发。

## 9. 如果看不明白，直接问
关键人物：Katie（A，产品+基建）、Raphael-LEI（B）、touhouzigei-crypto（C）。
