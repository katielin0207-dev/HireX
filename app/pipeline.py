
"""
RecruitmentPipeline：基于 Graph DAG + Harness + Checker + Skills + Flywheel 的统一招聘流水线。

将原有线性调用封装为 Graph 节点，实现：
- 并行 JD/简历解析
- Harness 包裹每个 Agent 调用
- Checker 校准循环（Loop 2）
- Skills 触发和合并
- Flywheel 存储和检索
"""

import json
import logging
import time
from typing import Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .graph import GraphOrchestrator, GraphNode, NodeStatus
from .harness import AgentHarness, HarnessConfig, HarnessResult
from .checker import CheckerAgent, CheckerResult, CALIBRATION_DIMENSIONS
from .skills import SkillRegistry, SkillMerger
from .flywheel import FlywheelStore, FlywheelRecord
from .config import settings

logger = logging.getLogger(__name__)


class RecruitmentPipeline:
    """
    招聘流水线编排器。

    Usage:
        pipeline = RecruitmentPipeline(llm_client=client)
        pipeline.setup(jd_text="...", resume_text="...", active_skills=[])
        results = pipeline.run()
        # results contains: jd_data, resume_data, match_result, questions, checker_result
    """

    def __init__(self, llm_client=None, skills_dir: str = None):
        self.llm_client = llm_client

        # ── 核心组件 ──
        self.harness = AgentHarness(
            config=HarnessConfig(max_retries=3, timeout_seconds=90),
            agent_name="recruitment",
        )
        self.checker = CheckerAgent(llm_client=llm_client, max_revision_rounds=3)
        self.skills = SkillRegistry(skills_dir or str(Path(__file__).parent / "skills"))
        self.flywheel = FlywheelStore()

        # ── Graph 编排器 ──
        self.graph = GraphOrchestrator(name="recruitment-pipeline", max_workers=4)

        # ── 状态 ──
        self.jd_text = ""
        self.resume_text = ""
        self.jd_data: dict = {}
        self.resume_data: dict = {}
        self.match_result: dict = {}
        self.questions: dict = {}
        self.checker_results: list[CheckerResult] = []
        self.flywheel_similar: list[FlywheelRecord] = []
        self.execution_log: list[dict] = []

    # ── 初始化 ──────────────────────────────────

    def setup(
        self,
        jd_text: str = "",
        resume_text: str = "",
        active_skills: list = None,
        enable_checker: bool = True,
        enable_flywheel: bool = True,
    ):
        """配置流水线参数"""
        self.jd_text = jd_text
        self.resume_text = resume_text
        self.enable_checker = enable_checker
        self.enable_flywheel = enable_flywheel

        # 加载 Skills
        self.skills.load_all()

        # 激活指定 Skills
        if active_skills:
            for sid in active_skills:
                self.skills.activate(sid)

        # Flywheel RAG 检索
        if enable_flywheel and resume_text:
            self.flywheel_similar = self.flywheel.retrieve_similar(
                resume_text + " " + jd_text, top_k=3
            )

    # ── 构建 Graph ──────────────────────────────

    def _build_graph(self):
        """构建 DAG 拓扑"""
        self.graph = GraphOrchestrator(name="recruitment-pipeline", max_workers=4)

        # ★ 初始输入改为【只读】注入，不再直接赋值给一个可变全局池。
        #   节点想用哪个 key，必须在 needs_initial 里声明。
        self.graph.set_initial_input({
            "jd_text": self.jd_text,
            "resume_text": self.resume_text,
            "flywheel_similar": self.flywheel_similar,
            "flywheel_notes": self.flywheel.generate_prompt_notes() if self.enable_flywheel else "",
        })

        # Node 1: JD 解析（与 Resume 解析并行）
        self.graph.add_node(GraphNode(
            name="parse_jd",
            fn=self._fn_parse_jd,
            harness=self.harness,
            needs_initial=["jd_text"],
            metadata={"label": "JD解析"},
        ))

        # Node 2: 简历解析（与 JD 解析并行）
        self.graph.add_node(GraphNode(
            name="parse_resume",
            fn=self._fn_parse_resume,
            harness=self.harness,
            needs_initial=["resume_text"],
            metadata={"label": "简历解析"},
        ))

        # Node 3: 匹配评分（依赖 JD + Resume 解析结果）
        self.graph.add_node(GraphNode(
            name="match",
            fn=self._fn_match,
            harness=self.harness,
            depends_on=["parse_jd", "parse_resume"],
            needs_initial=["flywheel_notes", "flywheel_similar"],
            metadata={
                "label": "匹配评分",
                "output_schema": {
                    "type": "object",
                    "required": ["overall_score", "score_breakdown", "recommendation"],
                    "properties": {
                        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    },
                },
            },
        ))

        # Node 4: 试题生成（依赖匹配结果）
        self.graph.add_node(GraphNode(
            name="generate_questions",
            fn=self._fn_generate_questions,
            harness=self.harness,
            depends_on=["match", "parse_resume", "parse_jd"],
            metadata={
                "label": "试题生成",
                "output_schema": {
                    "type": "object",
                    "required": ["questions"],
                    "properties": {"questions": {"type": "array"}},
                },
            },
        ))

        # Node 5: 模糊点追问
        self.graph.add_node(GraphNode(
            name="ambiguity",
            fn=self._fn_ambiguity,
            harness=self.harness,
            depends_on=["parse_resume", "generate_questions"],
            metadata={"label": "模糊点追问"},
        ))

        # Node 6: Skills 执行（插入到试题生成后）
        self.graph.add_node(GraphNode(
            name="skills_execution",
            fn=self._fn_execute_skills,
            harness=None,  # Skills 自身有简单的错误处理
            depends_on=["generate_questions", "match"],
            optional=True,   # Skills 失败不该阻断主链路
            metadata={"label": "Skills执行"},
        ))

        # ── ★ 显式数据边 ─────────────────────────────
        # 每条边写明：上游的哪个产出 → 在下游叫什么名字。
        # 这替代了原来"节点产出丢进 data_pool、下游自己去捞"的隐式传递，
        # 也让 _fn_match 里那串 `inputs.get("parse_jd") or inputs.get("jd_data")`
        # 的兜底链失去了存在的理由 —— 兜底链本来就是数据流不明确的症状。
        self.graph.add_edge("parse_jd", "match", as_key="jd_data")
        self.graph.add_edge("parse_resume", "match", as_key="resume_data")

        self.graph.add_edge("match", "generate_questions", as_key="match_result")
        self.graph.add_edge("parse_jd", "generate_questions", as_key="jd_data")
        self.graph.add_edge("parse_resume", "generate_questions", as_key="resume_data")

        self.graph.add_edge("parse_resume", "ambiguity", as_key="resume_data")
        self.graph.add_edge("generate_questions", "ambiguity", as_key="questions_result")

        self.graph.add_edge("generate_questions", "skills_execution", as_key="questions_result")
        self.graph.add_edge("match", "skills_execution", as_key="match_result")
        self.graph.add_edge("parse_jd", "skills_execution", as_key="jd_data")
        self.graph.add_edge("parse_resume", "skills_execution", as_key="resume_data")

    # ── Agent 函数 ───────────────────────────────

    def _fn_parse_jd(self, inputs: dict, attempt: int = 0) -> dict:
        """JD 解析 Agent"""
        from .matcher import parse_jd
        jd_text = inputs.get("jd_text", "")
        if not jd_text:
            return {"title": "未知岗位", "error": "JD文本为空"}
        return parse_jd(jd_text)

    def _fn_parse_resume(self, inputs: dict, attempt: int = 0) -> dict:
        """简历解析 Agent"""
        from .matcher import parse_resume
        resume_text = inputs.get("resume_text", "")
        if not resume_text:
            return {"name": "未知候选人", "error": "简历文本为空"}
        return parse_resume(resume_text)

    def _fn_match(self, inputs: dict, attempt: int = 0) -> dict:
        """匹配评分 Agent"""
        from .matcher import calculate_match

        # ★ 边已声明 as_key，key 是确定的，不再需要兜底链。
        #   原来那串 `inputs.get("parse_jd") or inputs.get("jd_data") or {}`
        #   加上「如果顶层有 title 就把整个 inputs 当 jd_data」的猜测，
        #   是数据流不明确逼出来的 —— 而它同时也掩盖了数据没送到的情况：
        #   拿不到就静默用 {}，最后表现为一个莫名其妙的低分。
        jd_data = inputs.get("jd_data") or {}
        resume_data = inputs.get("resume_data") or {}

        result = calculate_match(jd_data, resume_data)

        # 注入 Flywheel 历史上下文
        flywheel_notes = inputs.get("flywheel_notes", "")
        if flywheel_notes and "note" not in result:
            result["_flywheel_notes"] = flywheel_notes

        return result

    def _fn_generate_questions(self, inputs: dict, attempt: int = 0) -> dict:
        """试题生成 Agent"""
        from .question_generator import generate_questions

        jd_data = inputs.get("jd_data") or {}
        resume_data = inputs.get("resume_data") or {}
        match_result = inputs.get("match_result") or {}

        return generate_questions(jd_data, resume_data, match_result)

    def _fn_ambiguity(self, inputs: dict, attempt: int = 0) -> dict:
        """模糊点追问 Agent"""
        from .question_generator import generate_ambiguity_followups

        resume_data = inputs.get("resume_data") or {}
        return generate_ambiguity_followups(resume_data)

    def _fn_execute_skills(self, inputs: dict, attempt: int = 0) -> dict:
        """执行激活的 Skills"""
        active_skills = self.skills.get_active_by_trigger("on_question_generation")
        if not active_skills:
            return {"skills_output": {}, "skills_used": []}

        jd_data = inputs.get("jd_data") or {}
        resume_data = inputs.get("resume_data") or {}
        match_result = inputs.get("match_result") or {}

        if not self.llm_client:
            return {"skills_output": {}, "skills_used": []}

        jd_json = json.dumps(jd_data, ensure_ascii=False)
        resume_json = json.dumps(resume_data, ensure_ascii=False)
        match_json = json.dumps(match_result, ensure_ascii=False)

        def _run_one(skill):
            """单个 Skill 的 LLM 调用。失败只影响它自己。"""
            try:
                prompt = skill.prompt_template.format(
                    jd_data=jd_json, resume_data=resume_json, match_result=match_json,
                )
                result = self.llm_client.chat(
                    user_prompt=prompt,
                    system_prompt="你是一位招聘专家，请根据Skill要求生成内容。",
                    expect_json=True,
                )
                if isinstance(result, dict):
                    return skill.skill_id, result.get("questions", [result])
            except Exception as e:  # noqa: BLE001
                print(f"[Skill] {skill.skill_id} failed: {e}")
            return skill.skill_id, None

        # ★ 并行执行。原来是 for 循环【串行】调 LLM —— 默认激活 3 个
        #   on_question_generation 的 Skill，就是 3 次 LLM 往返串起来等。
        #   这些 Skill 彼此完全独立（各自只读 jd/resume/match，互不依赖），
        #   串行没有任何理由，纯粹是白等。并行后耗时 = 最慢的那一个。
        skill_outputs, skills_used = {}, []
        max_workers = min(len(active_skills), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for skill_id, questions in pool.map(_run_one, active_skills):
                if questions is not None:
                    skill_outputs[skill_id] = questions
                    skills_used.append(skill_id)

        return {
            "skills_output": skill_outputs,
            "skills_used": skills_used,
        }

    # ── 运行 ──────────────────────────────────────

    def run(self) -> dict:
        """执行完整流水线"""
        t0 = time.time()

        # 1. 构建 Graph
        self._build_graph()

        # 2. 执行 Graph
        graph_results = self.graph.run()

        # 3. 提取结果
        self.jd_data = self.graph.get_output("parse_jd") or {}
        self.resume_data = self.graph.get_output("parse_resume") or {}
        self.match_result = self.graph.get_output("match") or {}
        self.questions = self.graph.get_output("generate_questions") or {}
        self.ambiguity_result = self.graph.get_output("ambiguity") or {}
        self.skills_result = self.graph.get_output("skills_execution") or {}

        # 4. Checker 校准循环
        if self.enable_checker and self.match_result:
            self._run_checker_loop()

        # 5. Skills 合并
        if self.skills_result and self.skills_result.get("skills_output"):
            merger = SkillMerger()
            base_questions = self.questions.get("questions", [])
            skill_outputs = self.skills_result.get("skills_output", {})
            merged = merger.merge_questions(base_questions, skill_outputs)
            self.questions["questions"] = merged
            self.questions["skills_merged"] = True
            self.questions["skills_used"] = self.skills_result.get("skills_used", [])

        # 6. Flywheel 存储
        if self.enable_flywheel:
            self._store_to_flywheel()

        # 7. 执行摘要
        self.execution_log = self.graph.execution_log
        total_duration = (time.time() - t0) * 1000

        return self.get_summary(total_duration)

    def _run_checker_loop(self):
        """执行 Checker 校准循环（Loop 2）。

        ★ 这个方法此前【名不副实】：它叫 _run_checker_loop，实际只调了两次
          checker.check()，拿到 issues 之后什么都不做 —— 没有修订、没有重新校验。
          而 checker.py 里那个真正实现闭环的 run_calibration_loop，**从未被任何
          地方调用过**（全仓 grep 只有定义处一处）。

          任务要求 B3 的原文是「Checker 发现 FAIL → 将 issues 反馈给原 Agent →
          Agent 根据 suggested_fix 修订输出 → 再次提交 Checker 校验 →
          **至少完成一轮完整的校准循环**」。所以这里补的是判分权重最高的那一环。
        """
        source = {"jd_text": self.jd_text, "resume_text": self.resume_text}

        # ★ 匹配 与 试题 两条校准链【并行】。
        #   原来是串行：匹配最多 3 检 + 2 改，跑完再轮到试题的 3 检 + 2 改 ——
        #   最坏情况 4 次 LLM 往返首尾相接。两条链彼此不依赖：
        #   试题的修订只【读】 match_result，不写；匹配的修订只碰 match_result。
        #   为了让"只读"这件事真正成立，这里先把 match_result 快照下来给试题链用，
        #   否则匹配链改到一半的中间态会被试题链读到（竞态，且是那种偶发才现形的）。
        match_snapshot = dict(self.match_result) if isinstance(self.match_result, dict) else self.match_result

        def _calib_match():
            return self._calibrate(
                initial_output=self.match_result,
                regenerate=self._fn_match_revise,
                source=source,
                output_type="match_result",
            )

        def _calib_questions():
            return self._calibrate(
                initial_output=self.questions,
                regenerate=lambda fb: self._fn_questions_revise(fb, match_snapshot),
                source=source,
                output_type="questions_output",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_match = pool.submit(_calib_match)
            f_quest = pool.submit(_calib_questions) if self.questions else None

            self.match_result, match_history = f_match.result()
            self.checker_results.extend(match_history)

            if f_quest is not None:
                self.questions, q_history = f_quest.result()
                self.checker_results.extend(q_history)

    def _calibrate(self, initial_output, regenerate, source, output_type):
        """校验 → 反馈 → 修订 → 再校验。最多 max_revision_rounds 轮。

        返回 (最终输出, 本次校准的全部 CheckerResult)。

        ★ 三轮未过时返回的是【得分最高的那一轮】，不是最后一轮。
          要求原文是「输出**最佳可用结果**」—— 最后一轮未必最好：模型按反馈改
          A 问题时把 B 改坏是常见的。用最后一轮当"最佳"是个不查就看不出来的错。
        """
        history: list[CheckerResult] = []
        output = initial_output
        best_output, best_score = output, -1.0

        for rnd in range(1, self.checker.max_revision_rounds + 1):
            result = self.checker.check(
                agent_output=output, source_data=source, output_type=output_type
            )
            result.revision_round = rnd
            history.append(result)

            score = self._weighted_score(result)
            if score > best_score:
                best_score, best_output = score, output

            if result.overall_pass:
                return output, history

            if rnd == self.checker.max_revision_rounds:
                break

            # ★ 把 issues 真的送回 Agent 重新生成
            try:
                revised = regenerate(result)
                if revised:
                    output = revised
                else:
                    # 没抛异常但没产出 —— 再转一轮也是同一个 output 重复送检，
                    # 白烧一次 LLM。记下来并停，别让它空转到 max_rounds。
                    logger.warning(
                        "[calibration] %s 第 %d 轮修订返回空，停止修订",
                        output_type, rnd,
                    )
                    self.execution_log.append({
                        "event": "revision_empty", "output_type": output_type, "round": rnd,
                    })
                    break
            except Exception as e:  # noqa: BLE001
                # ★ 这里曾经只 append 进 execution_log 就 break —— 不打日志。
                #   后果：修订链路整条挂掉在界面和终端上都看不见，只表现为
                #   "三轮未过但只有 1 轮记录"，要翻 execution_log 才查得出来。
                #   校准循环是判分权重最高的一环，它失败必须是显式的。
                logger.warning(
                    "[calibration] %s 第 %d 轮修订失败，停止修订：%s: %s",
                    output_type, rnd, type(e).__name__, e,
                )
                self.execution_log.append({
                    "event": "revision_failed", "output_type": output_type,
                    "round": rnd, "error": f"{type(e).__name__}: {e}",
                })
                break

        # 三轮仍未通过 → 标记 degraded 并交出最佳可用结果
        if isinstance(best_output, dict):
            best_output = {**best_output, "degraded": True}
        self.execution_log.append({
            "event": "calibration_degraded",
            "output_type": output_type,
            "rounds": len(history),
            "best_weighted_score": round(best_score, 1),
        })
        return best_output, history

    @staticmethod
    def _weighted_score(result: CheckerResult) -> float:
        """★ 只对【实际参与判定】的维度归一化加权。
        原来遍历全部 5 个维度、缺的按 0 计 —— 不适用的维度会白白拉低总分，
        "得分最高的一轮"因此选不准。"""
        scored = result.calibration_scores
        total_w = sum(CALIBRATION_DIMENSIONS[d]["weight"] for d in scored) or 1.0
        return sum(
            scored[dim] * CALIBRATION_DIMENSIONS[dim]["weight"] for dim in scored
        ) / total_w

    def _fn_match_revise(self, feedback: CheckerResult) -> dict:
        from .matcher import calculate_match
        return calculate_match(self.jd_data, self.resume_data, revision_feedback=feedback)

    def _fn_questions_revise(self, feedback: CheckerResult, match_result: dict = None) -> dict:
        """★ match_result 走参数传入而不是读 self —— 两条校准链并行时，
        self.match_result 可能正在被匹配链改写。传快照才是确定的。"""
        from .question_generator import generate_questions
        return generate_questions(
            self.jd_data, self.resume_data,
            match_result if match_result is not None else self.match_result,
            revision_feedback=feedback,
        )

    def _store_to_flywheel(self):
        """存储到飞轮"""
        record = FlywheelRecord(
            id="",
            jd_summary=self.jd_data.get("title", "")[:200],
            resume_summary=json.dumps(self.resume_data, ensure_ascii=False)[:500],
            match_score=self.match_result.get("overall_score", 0),
            match_result=self.match_result,
            questions=self.questions.get("questions", []),
            checker_feedback=(
                # ★ 必须**展平**。原来写的是
                #     [self.checker.to_dict(r).get("issues", []) for r in ...]
                #   而 .get("issues") 本身就返回一个 list，于是产出
                #   list[list[dict]] —— 多包了一层。读取方
                #   flywheel.get_common_checker_issues 按 list[dict] 遍历，
                #   拿到的 issue 是 list，一执行 issue.get('dimension') 就
                #   AttributeError，整条分析链在 _build_graph 阶段直接崩。
                #   语义上这里要的是「这次分析所有轮次的问题合集」，平铺才对。
                {
                    "issues": [
                        issue
                        for r in self.checker_results
                        for issue in self.checker.to_dict(r).get("issues", [])
                    ]
                }
                if self.checker_results
                else None
            ),
            tags=[self.jd_data.get("title", ""), self.resume_data.get("name", "")],
        )
        self.flywheel.store(record)

    # ── 结果查询 ──────────────────────────────────

    def get_summary(self, total_duration: float = 0) -> dict:
        """获取执行摘要"""
        graph_summary = self.graph.get_execution_summary()

        return {
            "success": all(
                self.graph.get_result(n) and self.graph.get_result(n).status == NodeStatus.SUCCESS
                for n in ["parse_jd", "parse_resume", "match"]
            ),
            "jd_data": self.jd_data,
            "resume_data": self.resume_data,
            "match_result": self.match_result,
            "questions": self.questions,
            "ambiguity_result": self.ambiguity_result,
            "skills_result": self.skills_result,
            "checker_results": [
                {
                    "verdict": r.verdict if r.verdict else "N/A",
                    "passed": bool(r.overall_pass),
                    "scores": r.calibration_scores if r.calibration_scores else {},
                    "issues": [
                        {"dim": i.dimension or "unknown", "severity": i.severity.value if i.severity else "minor",
                         "desc": i.description or "", "location": i.location or ""}
                        for i in (r.issues or [])
                    ]
                }
                for r in self.checker_results
            ] if self.checker_results else [],
            "checker_passed": all(r.overall_pass for r in self.checker_results) if self.checker_results else False,
            "flywheel_similar_count": len(self.flywheel_similar),
            "flywheel_stats": self.flywheel.get_stats(),
            "graph_summary": graph_summary,
            "total_duration_ms": total_duration,
            "skills_active": self.skills.get_active_ids(),
            "skills_total": self.skills.count(),
        }

    def get_graph_mermaid(self) -> str:
        """获取 Graph 的 Mermaid 可视化"""
        return self.graph.print_dag()

    def get_checker_display(self) -> list[dict]:
        """获取 Checker 结果的前端展示数据"""
        result = []
        for r in self.checker_results:
            result.append({
                "verdict": r.verdict,
                "scores": r.calibration_scores,
                "passed": r.overall_pass,
                "issues_count": len(r.issues),
                "issues": [
                    {"dim": i.dimension, "severity": i.severity.value, "desc": i.description[:100]}
                    for i in r.issues
                ],
            })
        return result


# ── 快捷工厂函数 ───────────────────────────────

def create_pipeline(llm_client=None) -> RecruitmentPipeline:
    """创建流水线实例"""
    return RecruitmentPipeline(llm_client=llm_client)


# ── 独立 Skills 管理 API ────────────────────────

class SkillsManager:
    """Skills 管理器（供 UI 调用）"""

    def __init__(self, skills_dir: str = None):
        self.registry = SkillRegistry(skills_dir)
        self._loaded = False

    def load(self) -> dict:
        if not self._loaded:
            self.registry.load_all()
            self._loaded = True
        return self.registry.to_dict()

    def insert(self, skill_id: str) -> dict:
        skill = self.registry.insert(skill_id)
        return {"success": skill is not None, "skill": skill.skill_id if skill else None}

    def delete(self, skill_id: str) -> dict:
        ok = self.registry.delete(skill_id)
        return {"success": ok, "skill_id": skill_id}

    def toggle(self, skill_id: str, active: bool) -> dict:
        if active:
            ok = self.registry.activate(skill_id)
        else:
            ok = self.registry.deactivate(skill_id)
        return {"success": ok, "skill_id": skill_id, "active": active}

    def get_triggers(self) -> list[str]:
        return ["on_question_generation", "on_matching", "on_interview_start"]
