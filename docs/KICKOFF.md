# 24 小时 MVP 开工包（A 已备好，开工即拿即用）

> 本文档 = 开工包使用说明。作战计划见项目根目录的《24小时MVP作战计划.md》。

## 开工包里有什么

```
AI-recruitment-system/
├── docs/CONTRACT.md          ← 数据契约（先读这个，开工前 30 分钟全员对齐）
├── app/shared/               ← 公共件（只用，不改）
│   ├── llm.py                ← call_llm()：统一 LLM 调用（已验证 DeepSeek 连通）
│   ├── store.py              ← 候选人/JD 的 JSON 存取
│   ├── parallel.py           ← map_llm()：批量并发调用（限流3并发）
│   └── demo_cache.py         ← 演示模式缓存（演示翻车保险）
├── app/views/_template.py    ← 参考实现：新页面的标准写法，复制改名即用
├── mock/
│   ├── resumes/              ← 10 份测试简历（3优/4中/3风险，已生成）
│   ├── candidate_examples/   ← 3 个候选人 JSON 示例 + jd.json（提交到 git）
│   ├── demo_cache/           ← 演示缓存（A 后期预跑填充）
│   └── gen_*.py              ← Mock 数据生成脚本（可重跑）
├── sessions/                 ← 运行时数据（.gitignore，不提交）
└── dev.sh                    ← 一键启动：./dev.sh ｜ 演示模式: ./dev.sh demo
```

## 每人开工三步

1. **读契约**：`docs/CONTRACT.md`，重点看第 2 节"字段责任矩阵"——你只能写自己负责的字段
2. **复制模板**：`cp app/views/_template.py app/views/你的模块.py`，按文件头注释改 4 处
3. **自测**：`./dev.sh` 启动，用 `sessions/candidates/` 里的 3 个示例候选人数据开发

## 各人文件归属（冲突预防）

| 人 | 新建/负责的文件 | 禁止碰的文件 |
|----|----------------|-------------|
| A | `app/shared/`、`mock/`、`dev.sh`、`main.py` 导航 | 别人的页面和引擎 |
| B | `app/views/analysis.py`、`app/rule_engine.py` | `shared/`、`main.py` |
| C | `app/views/risk.py`、`app/risk_engine.py` | `shared/`、`main.py` |
| D | `app/views/interview_eval.py`、`app/evaluation.py` | `shared/`、`main.py` |
| E | `app/views/talent.py`、`app/talent_pool.py` | `shared/`、`main.py` |

页面写好后把 `render` 函数名发给 A，A 统一注册到导航。

## Git 约定

- 分支：`feat/infra`（A）、`feat/screening`（B）、`feat/risk`（C）、`feat/interview`（D）、`feat/talent`（E）
- 合并点：第 6 / 10 / 14 小时，由 A 执行
- `sessions/` 下运行时数据不提交；`mock/` 下共享数据必须提交

## 已验证（A 已完成）

- [x] DeepSeek API 连通（call_llm 实测返回正常）
- [x] 存储读写（save/load/update/list 全部通过）
- [x] 并发工具（map_llm 顺序保持）
- [x] 演示缓存读写
- [x] 10 份简历 + 3 个候选人示例 + JD 已生成
