# 数据契约 v1.0（开工前全员确认，改动必须群内广播）

> 本文件是五个模块并行开发的**唯一数据标准**。
> 规则：模块之间**禁止互相 import**，只通过 `sessions/candidates/{id}.json` 交换数据。
> 改字段名/加字段 → 先在群里说，再改这个文件，最后改代码。

---

## 1. 候选人主记录 `sessions/candidates/{candidate_id}.json`

```json
{
  "id": "cand_001",
  "name": "李晓峰",
  "resume_text": "简历原文（完整文本）",
  "resume_file": "mock/resumes/01_李晓峰_优秀.txt",
  "resume_parsed": {
    "education": [{"school": "浙江大学", "degree": "本科", "major": "软件工程", "start": "2018.09", "end": "2022.06"}],
    "experience": [{"company": "某金融科技公司", "title": "后端开发工程师", "start": "2023.03", "end": "至今"}],
    "skills": ["Python", "FastAPI", "MySQL", "Redis"],
    "total_years": 3.0
  },

  "match_result": {
    "overall_score": 82,
    "hard_score": 88,
    "soft_score": 74,
    "recommendation": "推进 | 待定 | 不推进",
    "breakdown": {
      "skills_match": {"score": 90, "reason": "..."},
      "experience_match": {"score": 78, "reason": "..."},
      "education_match": {"score": 100, "reason": "..."},
      "project_relevance": {"score": 85, "reason": "..."}
    },
    "matched_points": ["匹配点1", "匹配点2"],
    "gap_points": ["差距点1"],
    "summary": "一句话总结"
  },

  "risk_report": {
    "level": "低 | 中 | 高",
    "risks": [
      {"type": "经历断层 | 频繁跳槽 | 证书过期 | 信息存疑 | 技能存疑",
       "severity": "high | medium | low",
       "detail": "具体描述",
       "evidence": "简历原文引用"}
    ],
    "interview_focus": ["建议面试重点核实的问题1", "问题2"]
  },

  "interview_eval": {
    "rating": "A | B | C | D",
    "dimension_scores": {"专业能力": 85, "沟通表达": 78},
    "summary": "面试表现总结",
    "concerns": ["关注点1"],
    "form_filled": {}
  },

  "talent_profile": {
    "version": 1,
    "jd_signature": "当前JD内容指纹；JD变化后自动重算",
    "generated_for": {"title": "Python 后端开发工程师"},
    "categories": [
      {"key": "job_direction", "label": "岗位方向", "tags": [
        {"label": "工程师/技术方向", "source": "当前JD + 简历工作经历", "evidence": "原始依据", "reason": "AI判断说明", "confidence": 94}
      ]},
      {"key": "professional_skills", "label": "专业技能", "tags": []},
      {"key": "experience_background", "label": "经验背景", "tags": []},
      {"key": "general_competency", "label": "通用能力", "tags": []}
    ],
    "reuse_priority": {
      "score": 86.1,
      "level": "优先联系 | 建议复用 | 培养型储备 | 暂不推荐",
      "hard_gate": true,
      "components": {"当前JD匹配": 91, "历史面试": 90, "证据完整度": 100},
      "explanation": "当前岗位复用优先级计算说明"
    }
  },

  "status": "new | screened | risk_checked | interviewed | in_pool | offered | declined",
  "tags": ["Python", "3年经验", "RAG"],
  "updated_at": "2026-08-15T10:00:00"
}
```

## 2. 字段责任矩阵（谁写、谁读）

| 字段 | 写入方 | 读取方 |
|------|--------|--------|
| `id / name / resume_text` | A（Mock）/ B（上传时） | 全员 |
| `resume_parsed` | B | C、D |
| `match_result` | B | D、E |
| `risk_report` | C | D、E |
| `interview_eval` | D | E |
| `talent_profile` | E（入库或JD变化时自动生成） | E；其他模块可选读 |
| `status / tags` | B/C/D 都可更新 | E |
| `updated_at` | 谁写谁更新 | 全员 |

**铁律：只读别人写的字段，只写自己负责的字段。不要动别人的字段。**

## 3. JD 记录 `sessions/jd.json`

```json
{
  "title": "Python 后端开发工程师",
  "raw_text": "JD 原文",
  "requirements": {
    "hard": {
      "degree": "本科",
      "min_years": 3,
      "must_skills": ["Python", "FastAPI", "MySQL", "Redis"],
      "nice_skills": ["Elasticsearch", "Go", "Kubernetes"]
    },
    "soft": ["沟通协作", "学习能力", "抗压能力"]
  }
}
```

## 4. 状态枚举（status 只允许这几个值）

`new` → 新导入 → `screened` 已筛选 → `risk_checked` 已风险检测 → `interviewed` 已面试 → `in_pool` 已入库 / `offered` 已发offer / `declined` 候选人放弃

## 5. 共享工具函数（A 提供，`app/shared/`）

```python
from app.shared import call_llm, save_candidate, load_candidate, list_candidates

# LLM 调用（内部走项目已有的 LLMClient，自带重试和JSON修复）
result = call_llm("你的prompt", system="你是...", expect_json=True)

# 候选人存储
save_candidate({"id": "cand_001", ...})      # 新增或整体覆盖
cand = load_candidate("cand_001")             # 读取整个 JSON
update_candidate("cand_001", "risk_report", {...})  # 只更新自己的字段
all_cands = list_candidates()                 # 列出全部候选人
```

## 6. 目录约定

```
sessions/candidates/   # 候选人 JSON（运行时数据，.gitignore）
sessions/jd.json       # 当前 JD
mock/resumes/          # 10 份测试简历（A 提供，提交到 git）
mock/demo_cache/       # 演示模式缓存（A 预跑结果，提交到 git）
docs/CONTRACT.md       # 本文件
```
