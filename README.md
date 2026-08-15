# HireX 招聘甄选 AI 智能体

面向海信容声 HR 与用人部门的企业招聘辅助系统。产品以现有内部系统和北森为业务基座，Demo 使用本地 JSON 模拟数据交换，不替代人工筛选、录用、背调或审批。

## MVP 主流程

1. **简历筛选**：生成并编辑 JD，批量解析简历，输出硬性分、软性分、总分与证据。
2. **风险核验**：识别经历断层、频繁跳槽、证书异常、信息与技能存疑。
3. **面试辅助**：生成结构化及个性化问题；输入面试记录后生成纪要、评分与评价表。
4. **人才评价**：横向对比候选人，合格人才自动入库；Offer 放弃后自动推荐备选。

所有 AI 输出均保留人工确认入口。

## 本地启动

```bash
cp .env.example .env
# 在 .env 中填写 DeepSeek API Key
./dev.sh
```

不调用 API 的演示模式：

```bash
./dev.sh demo
```

打开 <http://127.0.0.1:8501>。

## 团队模块接口

模块之间只通过 `sessions/candidates/{id}.json` 交换数据：

| 模块 | 主要写入字段 |
|---|---|
| 简历筛选 | `resume_parsed`、`match_result`、`status=screened` |
| 风险核验 | `risk_report`、`status=risk_checked` |
| 面试辅助 | `interview_eval`、`status=interviewed` |
| 人才评价 | `status=offered/in_pool/declined` |

详细字段见 [`docs/CONTRACT.md`](docs/CONTRACT.md)。

## AI 工程层

为保证招聘结论可解释、可追溯、可降级，保留以下核心能力：

- `app/harness.py`：输入校验、重试、输出校验和降级。
- `app/graph.py`：招聘任务 DAG 编排。
- `app/checker.py`：结果一致性、证据引用和幻觉校验。
- `app/pipeline.py`：核心能力的统一编排入口。

比赛版前端不展示通用 Skills 管理、语音面试、虚拟人或旧版模拟面试页面，以保持主链路清晰。

## 当前目录

```text
app/
  main.py                 四模块统一导航
  views/screening.py      简历筛选
  views/risk.py           风险核验（B 合并后自动接入）
  views/interview_eval.py 面试辅助（B 合并后自动接入）
  views/talent.py         人才评价
  talent_pool.py          人才决策与备选推荐
  shared/                 数据、模型和缓存公共件
mock/                     演示简历和候选人
sessions/                 运行时数据（不提交）
tests/                    自动测试
```
