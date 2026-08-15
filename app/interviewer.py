"""
面试官 Agent 核心模块：实现有状态、有记忆、有策略的AI面试官。

状态机：INIT -> INTRODUCTION -> QUESTIONING -> EVALUATING -> REFLECTING -> (loop) -> REPORTING

题库注入模式（新增）：支持从分析环节题库中随机抽取题目注入，实现分析→面试无缝衔接
"""
import json
from datetime import datetime
from typing import Any, Optional

from .config import settings
from .llm_client import llm_client, LLMError
from .prompts import (
    INTERVIEWER_SYSTEM_PROMPT,
    JD_PARSE_PROMPT,
    RESUME_PARSE_PROMPT,
    PERSONA_GEN_PROMPT,
    OPENING_PROMPT,
    EVALUATE_AND_DECIDE_PROMPT,
)


class InterviewError(Exception):
    """面试流程异常"""
    pass


class InterviewState:
    """面试状态枚举"""
    INIT = "init"
    INTRODUCTION = "introduction"
    QUESTIONING = "questioning"
    EVALUATING = "evaluating"
    REFLECTING = "reflecting"
    REPORTING = "reporting"
    DONE = "done"


class InterviewerAgent:
    """
    AI 面试官 Agent

    核心职责：
    1. 解析 JD + 简历
    2. 初始化面试官人格
    3. 管理多轮对话
    4. 动态追问决策（反思机制）
    5. 记录评估数据供报告生成

    题库注入模式（新增）：
    - inject_questions() 接收从分析环节抽取的题目
    - 面试按序使用注入题目，追问时动态生成
    - remaining_pool 作为切换维度时的备选题源
    """

    def __init__(self, max_rounds: int = None):
        self.max_rounds = max_rounds or settings.DEFAULT_MAX_ROUNDS
        self.state = InterviewState.INIT

        # 结构化数据
        self.jd_data: dict = {}
        self.resume_data: dict = {}
        self.persona: dict = {}

        # 面试记录
        self.turns: list[dict] = []
        self.covered_dimensions: list[str] = []
        self.pending_dimensions: list[str] = []
        self.conversation_history: list[dict] = []
        self.overall_impression: str = ""

        # LLM 配置
        self.temperature = settings.TEMPERATURE

        # 题库注入（新增）
        self.injected_questions: list[dict] = []   # 注入的题目
        self.remaining_pool: list[dict] = []        # 未使用题库（备选）
        self.question_index: int = 0                # 当前题库指针
        self.use_injected_mode: bool = False         # 是否使用注入模式

    # ── 题库注入（新增） ────────────────────────────────
    def inject_questions(self, questions: list[dict], remaining_pool: list[dict] = None):
        """
        从分析环节注入题目到面试中。

        调用时机：简历分析Tab完成后，用户点击[开始AI面试]时

        Args:
            questions: 从题库抽取的题目列表（含完整元信息）
            remaining_pool: 未被抽取的剩余题目（备选题源）
        """
        self.injected_questions = questions
        self.remaining_pool = remaining_pool or []
        self.question_index = 0
        self.use_injected_mode = True

    def _get_next_injected_question(self) -> Optional[dict]:
        """获取下一道注入的题目（题库指针前移）"""
        if self.question_index < len(self.injected_questions):
            q = self.injected_questions[self.question_index]
            self.question_index += 1
            return q
        return None

    def _get_question_from_pool(self, dimension: str = None) -> Optional[dict]:
        """从 remaining_pool 中按维度取题"""
        if not self.remaining_pool:
            return None

        if dimension:
            # 优先按维度匹配
            candidates = [q for q in self.remaining_pool if q.get("category") == dimension]
            if candidates:
                q = candidates[0]
                self.remaining_pool.remove(q)
                return q

        # 随机取一题
        import random
        q = random.choice(self.remaining_pool)
        self.remaining_pool.remove(q)
        return q

    # ── Phase 1: 文档解析 ─────────────────────────────
    def parse_documents(self, jd_text: str, resume_text: str) -> dict:
        """解析 JD 和简历为结构化数据"""
        jd_result = llm_client.chat(
            user_prompt=JD_PARSE_PROMPT.format(jd_text=jd_text),
            expect_json=True,
            temperature=settings.EVAL_TEMPERATURE,
        )
        self.jd_data = jd_result

        resume_result = llm_client.chat(
            user_prompt=RESUME_PARSE_PROMPT.format(resume_text=resume_text),
            expect_json=True,
            temperature=settings.EVAL_TEMPERATURE,
        )
        self.resume_data = resume_result

        return {"jd_data": self.jd_data, "resume_data": self.resume_data}

    def load_parsed_data(self, jd_data: dict, resume_data: dict):
        """
        直接注入已解析的结构化数据（跳过 LLM 解析）。
        用于复用简历分析Tab的解析结果。
        """
        self.jd_data = jd_data
        self.resume_data = resume_data

    # ── Phase 2: 初始化面试官 ──────────────────────────
    def initialize_persona(self) -> dict:
        """根据 JD 生成面试官人格和面试策略"""
        jd_json = json.dumps(self.jd_data, ensure_ascii=False, indent=2)
        persona_result = llm_client.chat(
            user_prompt=PERSONA_GEN_PROMPT.format(jd_json=jd_json),
            expect_json=True,
            temperature=settings.TEMPERATURE,
        )
        self.persona = persona_result

        all_dims = ["技术基础", "项目经验", "系统设计", "行为面试", "职业规划", "模糊点验证"]
        weights = self.persona.get("dimension_weights", {})
        sorted_dims = sorted(all_dims, key=lambda d: weights.get(
            {"技术基础": "technical_depth", "项目经验": "project_experience",
             "系统设计": "system_design", "行为面试": "communication",
             "职业规划": "culture_fit", "模糊点验证": "technical_depth"}.get(d, 50)
        ), reverse=True)
        self.pending_dimensions = sorted_dims

        sys_prompt = INTERVIEWER_SYSTEM_PROMPT.format(
            persona_name=self.persona.get("persona_name", "面试官"),
            position=self.jd_data.get("title", "未知岗位"),
            persona_style=self.persona.get("persona_style", "专业、公正"),
            resume_summary=self.resume_data.get("summary", self.resume_data.get("self_evaluation", "")),
            jd_summary=json.dumps(self.jd_data, ensure_ascii=False),
            interview_strategy=self.persona.get("interview_strategy", ""),
        )

        self.system_prompt = sys_prompt
        self.conversation_history = [{"role": "system", "content": sys_prompt}]

        return self.persona

    # ── Phase 3: 生成开场白 ────────────────────────────
    def generate_opening(self) -> tuple[str, str]:
        """生成面试开场白和第一个问题"""
        self.state = InterviewState.INTRODUCTION

        resume_key_points = json.dumps({
            "name": self.resume_data.get("name", ""),
            "skills": self.resume_data.get("skills", [])[:5],
            "projects": [p.get("name") for p in self.resume_data.get("projects", [])[:3]],
            "experience": [e.get("company") for e in self.resume_data.get("experience", [])[:3]],
        }, ensure_ascii=False)

        ambiguous = json.dumps(
            self.resume_data.get("ambiguous_points", []),
            ensure_ascii=False
        )

        # 注入的题库摘要
        injected_summary = ""
        if self.use_injected_mode and self.injected_questions:
            injected_summary = "已注入题库（共{}题）：\n".format(len(self.injected_questions))
            for i, q in enumerate(self.injected_questions[:5]):
                injected_summary += f"  {i+1}. [{q.get('category', '')}] {q.get('question', '')[:60]}\n"

        result = llm_client.chat(
            user_prompt=OPENING_PROMPT.format(
                resume_key_points=resume_key_points,
                ambiguous_points=ambiguous,
                strategy=self.persona.get("interview_strategy", ""),
                injected_questions=injected_summary,
            ),
            expect_json=True,
            temperature=self.temperature,
        )

        greeting = result.get("greeting", "你好，欢迎参加今天的面试。")
        first_question = result.get("first_question", "请简单介绍一下你自己。")

        self.conversation_history.append({"role": "assistant", "content": greeting})
        self.conversation_history.append({"role": "assistant", "content": first_question})

        self.turns.append({
            "round": 1,
            "question": first_question,
            "dimension": result.get("question_dimension", ""),
            "intent": result.get("question_intent", ""),
        })

        self.state = InterviewState.QUESTIONING
        return greeting, first_question

    # ── Phase 4: 处理用户回答 + 决策下一轮 ──────────────
    def process_answer(self, user_answer: str) -> dict:
        """
        处理候选人的回答：评估 → 反思 → 决策下一步

        Returns:
            {
                "interview_ongoing": bool,
                "message": str,
                "current_eval": dict,
                "next_action": str,
            }
        """
        current_turn = self.turns[-1]
        round_num = len(self.turns)

        eval_result = self._evaluate_answer(
            round_num=round_num,
            question=current_turn["question"],
            user_answer=user_answer,
        )

        current_turn["answer"] = user_answer
        current_turn["evaluation"] = {
            "score": eval_result.get("score", 0),
            "dimension": eval_result.get("dimension", ""),
            "answer_quality": eval_result.get("answer_quality", ""),
            "key_points_hit": eval_result.get("key_points_hit", []),
            "key_points_missed": eval_result.get("key_points_missed", []),
            "contradictions_found": eval_result.get("contradictions_found", []),
        }
        current_turn["reflection"] = eval_result.get("action_reason", "")

        self.conversation_history.append({"role": "user", "content": user_answer})

        dim = eval_result.get("dimension", "")
        if dim and dim not in self.covered_dimensions:
            self.covered_dimensions.append(dim)
        if dim in self.pending_dimensions:
            self.pending_dimensions.remove(dim)

        next_action = eval_result.get("next_action", "next_topic")

        # 仅在达到最大轮数时结束面试，不再因为 pending_dimensions 为空而提前终止
        if round_num >= self.max_rounds:
            next_action = "wrap_up"

        if next_action == "wrap_up":
            closing = self._generate_closing()
            self.conversation_history.append({"role": "assistant", "content": closing})
            self.state = InterviewState.REPORTING
            return {
                "interview_ongoing": False,
                "message": closing,
                "current_eval": eval_result,
                "next_action": "wrap_up",
            }

        # 生成下一个问题
        next_question = eval_result.get("next_question", "")
        if not next_question:
            # LLM没给出下一题 → 从注入题库或备选池取
            if self.use_injected_mode:
                next_q = self._get_next_injected_question()
                if next_q:
                    next_question = next_q.get("question", "")
                else:
                    # 题库用完，尝试从备选池取
                    pool_q = self._get_question_from_pool(dim)
                    next_question = pool_q.get("question", "") if pool_q else ""
            if not next_question:
                next_question = "感谢你的回答。让我们换个角度，请谈谈..."

        self.conversation_history.append({"role": "assistant", "content": next_question})
        next_dim = eval_result.get("next_dimension", "")

        self.turns.append({
            "round": round_num + 1,
            "question": next_question,
            "dimension": next_dim,
        })

        return {
            "interview_ongoing": True,
            "message": next_question,
            "current_eval": eval_result,
            "next_action": next_action,
        }

    def _evaluate_answer(self, round_num: int, question: str, user_answer: str) -> dict:
        """调用 LLM 评估答案并决策下一步"""
        summary_parts = []
        for t in self.turns:
            q = t.get("question", "")[:60]
            a = t.get("answer", "")[:60]
            summary_parts.append(f"Q{t['round']}: {q} -> A: {a}")
        conv_summary = "\n".join(summary_parts[-6:])

        # 构建剩余题库摘要
        pool_summary = ""
        if self.use_injected_mode:
            remaining = [q.get("question", "")[:80] for q in self.remaining_pool[:5]]
            if self.injected_questions and self.question_index < len(self.injected_questions):
                upcoming = [q.get("question", "")[:80] for q in self.injected_questions[self.question_index:self.question_index+3]]
                pool_summary = f"待注入题: {upcoming}\n备选题: {remaining}"
            else:
                pool_summary = f"备选题: {remaining}"

        result = llm_client.chat(
            user_prompt=EVALUATE_AND_DECIDE_PROMPT.format(
                round_num=round_num,
                max_rounds=self.max_rounds,
                current_question=question,
                user_answer=user_answer,
                covered_dimensions=", ".join(self.covered_dimensions) or "无",
                pending_dimensions=", ".join(self.pending_dimensions) or "无",
                remaining_pool=pool_summary,
                conversation_summary=conv_summary,
            ),
            expect_json=True,
            temperature=settings.EVAL_TEMPERATURE,
        )
        return result

    def _generate_closing(self) -> str:
        """生成面试结束语"""
        return (
            "非常感谢你的时间，我们的面试到此结束。"
            "我正在综合评估你的表现，请稍等片刻，评估报告即将生成..."
        )

    # ── 导出面试记录 ────────────────────────────────────
    def get_interview_data(self) -> dict:
        """导出完整面试数据供报告生成"""
        return {
            "jd_data": self.jd_data,
            "resume_data": self.resume_data,
            "persona": self.persona,
            "turns": self.turns,
            "covered_dimensions": self.covered_dimensions,
            "total_rounds": len(self.turns),
            "timestamp": datetime.now().isoformat(),
        }

    def get_transcript(self) -> str:
        """生成对话记录文本"""
        lines = []
        for t in self.turns:
            lines.append(f"【第{t['round']}轮】")
            lines.append(f"面试官：{t['question']}")
            if t.get("answer"):
                lines.append(f"候选人：{t['answer']}")
            if t.get("evaluation"):
                lines.append(f"[评分：{t['evaluation'].get('score', '?')}分]")
            lines.append("")
        return "\n".join(lines)
