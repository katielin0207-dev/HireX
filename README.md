# HireX · 海信—招聘甄选智能体

> 岗位千万条，匹配第一条。

HireX 是面向海信容声 HR 与用人部门的企业级招聘决策工作台。产品在现有企业招聘系统与北森流程之上补充 AI 能力，完成岗位标准生成、简历匹配、面试辅助、人才评价和录用前核验。

比赛 Demo 使用本地 JSON 模拟北森的数据读取与回写，不替代企业原有的人工决策、背调、审批和 Offer 发放流程。

## 最终产品流程

系统顶部保留三段业务导航：

```text
简历筛选（岗位 JD → 简历筛选 → 面试辅助）
                  ↓
               人才评价
                  ↓
               风险核验（录用前核验）
```

### 1. 简历筛选

该工作区包含三个连续步骤：

- **岗位 JD**：录入岗位、部门、学历、年限、技能和软实力要求，由 AI 生成可编辑 JD。
- **简历筛选**：批量分析候选人，输出 0–100 分匹配分，并分别展示硬性条件、软性素质和判断依据。
- **面试辅助**：为候选人生成专属 9 题面试包；输入面试记录后自动生成纪要、评分和评价表。

### 2. 人才评价

- 汇总简历、匹配分和面试评价，形成多候选人横向对比。
- 展示候选人的能力总览、维度分析和逐层可追溯证据。
- 为合格候选人生成岗位方向、专业技能、经验背景、通用能力四类人才标签。
- 支持合格人才入库、当前 JD 动态复用排序。
- 模拟首选人放弃 Offer 后，自动推荐下一位合格候选人补位。

### 3. 风险核验

本页面只保留**录用前核验**：

- 从人才评价结果中选择拟录用候选人。
- 上传第三方背调报告、学历证明、证书或其他授权材料。
- AI 解析 PDF、Word 或文本报告，整理待核验事项。
- 输出背调摘要、异常项、补充材料要求和下一步建议。
- 最终结论仍由 HR 人工确认，再进入企业 Offer 审批流程。

## AI 使用方式

HireX 不是简单的聊天框，而是“规则引擎 + 大模型 + 证据链 + 人工确认”的组合：

- 硬性条件（学历、年限、必备技能）由规则引擎计算。
- JD 文案、软性匹配、面试题、面试纪要和人才评价由大模型生成。
- 每个结论尽量保留来源、证据和置信度，支持向下查看原始材料。
- 所有筛选、录用、背调和 Offer 决策均保留人工确认入口。
- API 不稳定时可使用演示缓存，避免现场演示中断。

核心工程文件：

| 文件 | 作用 |
|---|---|
| `app/harness.py` | 输入校验、模型调用重试、输出校验与降级 |
| `app/graph.py` | 招聘任务流程编排 |
| `app/checker.py` | 结果一致性、证据引用与幻觉检查 |
| `app/pipeline.py` | AI 能力统一执行入口 |
| `app/shared/llm.py` | 页面共用的大模型调用接口 |

## 本地启动

### 最快启动方式

```bash
git clone https://github.com/katielin0207-dev/HireX.git
cd HireX
cp .env.example .env     # 填入团队私发的 DeepSeek API Key；暂时不填也能运行演示模式
./dev.sh                 # 一键启动（首次自动创建虚拟环境并安装依赖）
```

启动完成后访问：<http://127.0.0.1:8501>

### 1. 克隆项目

```bash
git clone https://github.com/katielin0207-dev/HireX.git
cd HireX
```

### 2. 配置模型（可选）

```bash
cp .env.example .env
```

编辑 `.env`：

```env
LLM_API_KEY=你的-DeepSeek-API-Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

不填写 Key 也能直接运行，系统会自动使用本地演示数据和可解释规则；填写有效 Key 后自动启用真实 AI。

请勿将真实 API Key 提交到 GitHub。

### 3. 部署成所有人可访问的真实 AI 网页

在 Streamlit Community Cloud 创建应用后，进入应用的 **Settings → Secrets**，填写：

```toml
LLM_API_KEY = "你的-DeepSeek-API-Key"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-v4-flash"
```

保存并重新启动应用。访问网页的人无需知道或填写 Key，所有真实模型请求都由部署端统一发出。

### 4. 启动

```bash
./dev.sh
```

浏览器打开：<http://127.0.0.1:8501>

不调用模型、只读取演示缓存：

```bash
./dev.sh demo
```

## 推荐 Demo 演示顺序

1. 在“岗位 JD”中载入质量工程师示例并生成岗位要求。
2. 进入“简历筛选”，展示候选人排名、硬性分、软性分和原文依据。
3. 进入“面试辅助”，展示候选人专属 9 题并粘贴模拟面试记录。
4. 推送至“人才评价”，对比 3 位候选人并查看能力证据。
5. 将合格候选人加入人才库，演示标签与复用排序。
6. 模拟首选人放弃 Offer，展示系统自动推荐备选人。
7. 进入“风险核验”，上传或展示第三方背调报告的录用前核验摘要。

## 数据与模块契约

岗位与候选人数据保存在本地运行目录：

```text
sessions/jd.json                 当前岗位 JD
sessions/candidates/{id}.json   候选人完整档案
```

主要字段：

| 字段 | 含义 |
|---|---|
| `resume_parsed` | 结构化简历 |
| `match_result` | 当前岗位匹配结果 |
| `interview_questions` | 候选人专属 9 题 |
| `interview_eval` | 面试纪要、评分与评价表 |
| `talent_profile` | 能力档案、证据与人才标签 |
| `preoffer_report` | 录用前核验摘要 |
| `status` | 候选人当前流程状态 |

完整字段说明见 [`docs/CONTRACT.md`](docs/CONTRACT.md)。

## 项目结构

```text
app/
  main.py                    全局导航与品牌外壳
  views/
    screening_flow.py        简历筛选工作区入口
    job_posting.py           JD 生成与编辑
    screening.py             候选人匹配与筛选
    interview_eval.py        9 题面试包与评价表
    talent.py                人才评价、人才库与 Offer 补位
    preoffer.py              录用前风险核验
  shared/                    模型、岗位、存储与缓存公共能力
  talent_pool.py             人才标签、排序和备选推荐逻辑
mock/                        演示岗位、简历和缓存数据
sessions/                    本地运行数据（不提交）
tests/                       自动测试
```

## 企业落地边界

- Demo 使用本地 JSON 模拟北森接口；正式落地时替换为企业授权 API。
- AI 输出只作为辅助判断，不自动淘汰候选人，不替代正式背景调查。
- 候选人数据、面试记录和背调材料应在企业授权的私有环境内处理。
- 正式版本需复用北森账号、权限、审批流和操作日志。

## 当前开发分支

三位成员模块整合与统一 UI 版本位于：

```text
integration/final-demo
```

合并到 `main` 前，请先完整走通一次上述 Demo 演示顺序。
