
"""
Checker Agent 校准循环（Loop 2）：对 Agent 输出进行五维校验，发现问题后反馈修订。

校准维度：
  1. 数据准确性 — 输出中的信息是否与简历/JD原文一致
  2. 归因正确性 — 评分理由是否引用了原文
  3. 格式合规     — 输出是否符合约定的JSON Schema
  4. 维度覆盖     — 面试题是否覆盖全部5个维度
  5. 幻觉检测     — 输出中是否有编造的信息

修订闭环：Agent输出 → Checker校验 → 发现问题 → 反馈修订 → 再校验（最多3轮）
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class Severity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class CalibrationIssue:
    """校准问题"""
    dimension: str          # 校准维度名
    severity: Severity
    location: str           # 问题位置（如 "match_result.matched_points[2]"）
    description: str        # 问题描述
    suggested_fix: str      # 修改建议
    evidence: str = ""      # 证据（简历/JD原文引用）


@dataclass
class CheckerResult:
    """Checker 校验结果"""
    verdict: str            # "PASS" | "FAIL"
    calibration_scores: dict[str, int]  # 各维度得分 (0-100)
    issues: list[CalibrationIssue] = field(default_factory=list)
    overall_pass: bool = True
    revision_round: int = 0
    summary: str = ""
    # ★ 对这种输出不成立、因而未参与判定的维度。
    #   展示时要明确标「不适用」而不是留空 —— 留空会被当成"没查"。
    skipped_dimensions: list[str] = field(default_factory=list)
    weighted_score: float = 0.0


# ── 五维校验规则定义 ──────────────────────────────

CALIBRATION_DIMENSIONS = {
    "数据准确性": {
        "weight": 0.25,
        "pass_threshold": 95,       # 一致性 ≥ 95%
        "description": "输出中的姓名/公司/年份/技能是否与简历原文一致",
        "check_fn": "check_data_accuracy",
    },
    "归因正确性": {
        "weight": 0.20,
        "pass_threshold": 80,
        "description": "每条匹配评分理由是否引用了简历/JD具体原文",
        "check_fn": "check_attribution",
    },
    "格式合规": {
        "weight": 0.15,
        "pass_threshold": 100,      # 必须100%合规
        "description": "输出是否完全符合约定的JSON Schema，必填字段是否完整",
        "check_fn": "check_format_compliance",
    },
    "维度覆盖": {
        "weight": 0.20,
        "pass_threshold": 80,
        "description": "面试题是否覆盖全部5个维度（技术基础/项目深挖/场景设计/行为面试/模糊点追问）",
        "check_fn": "check_dimension_coverage",
    },
    "幻觉检测": {
        "weight": 0.20,
        "pass_threshold": 95,
        "description": "输出中是否存在简历/JD中未提及的信息",
        "check_fn": "check_hallucination",
    },
}

REQUIRED_DIMENSIONS = ["技术基础", "项目深挖", "场景设计", "行为面试", "模糊点追问"]

# ── ★ 维度适用性 ────────────────────────────────────────────────
#
# 五个维度并非对每种输出都成立：
#
#   · 「维度覆盖」查的是 output["questions"] 覆盖了几个题型 ——
#     match_result 里【结构上就没有 questions】，于是恒为 0 分，
#     还附带一条 CRITICAL「面试题列表为空」。
#   · 「数据准确性」查的是 output 的 matched_points / gap_points ——
#     questions_output 里【结构上就没有这两个字段】，
#     accuracy_checks 恒为 0，score = int(0 / max(0,1) * 100) = 0。
#
# 两者都低于 pass_threshold，而 overall_pass 要求【全部维度】达标，
# 所以 **两条校准链都永远不可能 PASS**。后果是三重的：
#
#   1. 正确性：verdict 恒为 FAIL、结果恒被打上 degraded:true，
#      "自我校验"输出的信号是假的
#   2. 性能：每次分析都必然跑满 3 轮 = 4 次额外 LLM 重生成。
#      实测这一段占 273.9s 总耗时里的约 159s（试题重生成一次就要 60s）
#   3. 可信度：演示时评审看到的永远是"校验未通过"
#
# ★ `max(accuracy_checks, 1)` 是这个 bug 的指纹：写的人知道分母可能为 0，
#   于是防了除零 —— 但把"没什么可查"变成了"查了，0 分"。
#   防崩溃防对了，默认值取错了。
#
# 修法：不适用的维度【既不算 0 也不算 100】，而是排除在
# overall_pass 与加权总分之外。给 100 等于伪造通过，同样是假信号。
DIMENSION_APPLICABILITY = {
    "match_result": {"数据准确性", "归因正确性", "格式合规", "幻觉检测"},
    "questions_output": {"归因正确性", "格式合规", "维度覆盖", "幻觉检测"},
    "ambiguity_output": {"格式合规", "幻觉检测"},
}
# 未登记的 output_type 一律按全维度校验（保守：宁可多查）
DEFAULT_APPLICABLE = set(CALIBRATION_DIMENSIONS.keys())


def applicable_dimensions(output_type: str) -> set:
    return DIMENSION_APPLICABILITY.get(output_type, DEFAULT_APPLICABLE)

# ── 输出 Schema 定义 ──────────────────────────────

OUTPUT_SCHEMAS = {
    "match_result": {
        "required": ["overall_score", "score_breakdown", "matched_points", "gap_points", "recommendation"],
        "properties": {
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        },
    },
    "questions_output": {
        "required": ["questions", "category_stats", "difficulty_stats"],
        "properties": {
            "questions": {"type": "array"},
        },
    },
}


class CheckerAgent:
    """
    Checker Agent：对 Agent 输出进行五维校验。

    Usage:
        checker = CheckerAgent(llm_client=client)
        result = checker.check(
            agent_output=match_result,
            source_data={"jd_text": jd_text, "resume_text": resume_text},
            output_type="match_result",
        )
        if not result.overall_pass:
            # 反馈给 Agent 修订
            revised = agent.revise(feedback=result)
    """

    def __init__(self, llm_client=None, max_revision_rounds: int = 3):
        self.llm_client = llm_client
        self.max_revision_rounds = max_revision_rounds
        self.check_history: list[CheckerResult] = []

    def check(
        self,
        agent_output: dict,
        source_data: dict,
        output_type: str = "match_result",
    ) -> CheckerResult:
        """
        对 Agent 输出进行全面校验。

        Args:
            agent_output: Agent 的输出数据
            source_data: 原始数据（jd_text, resume_text, jd_data, resume_data等）
            output_type: 输出类型（match_result | questions_output | ambiguity_output）

        Returns:
            CheckerResult: 校验结果（含校准分和问题列表）
        """
        issues = []
        scores = {}
        # ★ 只跑【对这种输出成立】的维度，见 DIMENSION_APPLICABILITY 的说明
        applicable = applicable_dimensions(output_type)

        # ── 维度1：数据准确性 ──────────────────────
        if "数据准确性" in applicable:
            acc_score, acc_issues = self._check_data_accuracy(agent_output, source_data)
            scores["数据准确性"] = acc_score
            issues.extend(acc_issues)

        # ── 维度2：归因正确性 ──────────────────────
        if "归因正确性" in applicable:
            attr_score, attr_issues = self._check_attribution(agent_output, source_data)
            scores["归因正确性"] = attr_score
            issues.extend(attr_issues)

        # ── 维度3：格式合规 ──────────────────────
        if "格式合规" in applicable:
            fmt_score, fmt_issues = self._check_format_compliance(agent_output, output_type)
            scores["格式合规"] = fmt_score
            issues.extend(fmt_issues)

        # ── 维度4：维度覆盖 ──────────────────────
        if "维度覆盖" in applicable:
            dim_score, dim_issues = self._check_dimension_coverage(agent_output)
            scores["维度覆盖"] = dim_score
            issues.extend(dim_issues)

        # ── 维度5：幻觉检测 ──────────────────────
        if "幻觉检测" in applicable:
            hal_score, hal_issues = self._check_hallucination(agent_output, source_data)
            scores["幻觉检测"] = hal_score
            issues.extend(hal_issues)

        # ── 综合判定 ──────────────────────────────
        # ★ 加权分按【实际参与的维度】归一化，否则少跑一个维度会平白丢掉它的权重，
        #   两种输出类型的分数也就没法互相比较了。
        total_weight = sum(CALIBRATION_DIMENSIONS[d]["weight"] for d in scores) or 1.0
        weighted_score = sum(
            scores[dim] * CALIBRATION_DIMENSIONS[dim]["weight"] for dim in scores
        ) / total_weight
        overall_pass = all(
            scores[dim] >= CALIBRATION_DIMENSIONS[dim]["pass_threshold"] for dim in scores
        )

        # 生成摘要
        summary = self._generate_summary(scores, issues, overall_pass)

        result = CheckerResult(
            verdict="PASS" if overall_pass else "FAIL",
            calibration_scores=scores,
            issues=issues,
            overall_pass=overall_pass,
            summary=summary,
            skipped_dimensions=sorted(set(CALIBRATION_DIMENSIONS) - applicable),
            weighted_score=round(weighted_score, 1),
        )

        self.check_history.append(result)
        return result

    # ── 五维校验实现 ──────────────────────────────

    def _check_data_accuracy(
        self, output: dict, source: dict
    ) -> tuple[int, list[CalibrationIssue]]:
        """
        维度1：数据准确性。
        检查输出中的关键信息是否与原文一致。
        """
        issues = []
        resume_text = source.get("resume_text", "")
        jd_text = source.get("jd_text", "")
        all_text = (resume_text + " " + jd_text).lower()
        accuracy_checks = 0
        accuracy_passes = 0

        # 检查匹配评分中引用的技能是否存在于原文
        matched_points = output.get("matched_points", [])
        gap_points = output.get("gap_points", [])

        for point_list, point_type in [(matched_points, "matched"), (gap_points, "gap")]:
            for i, point in enumerate(point_list):
                if isinstance(point, dict):
                    text_to_check = point.get("point", "") or point.get("reason", "")
                else:
                    text_to_check = str(point)

                accuracy_checks += 1

                # 提取文本中的关键实体（技能词、公司名等）
                keywords = self._extract_keywords(text_to_check)
                found = any(kw.lower() in all_text for kw in keywords if len(kw) > 2)

                if not found and len(text_to_check) > 10:
                    issues.append(CalibrationIssue(
                        dimension="数据准确性",
                        severity=Severity.MAJOR,
                        location=f"{point_type}_points[{i}]",
                        description=f"匹配理由中的关键信息在原文中未找到: '{text_to_check[:80]}'",
                        suggested_fix=f"请引用简历或JD中的原文来支撑此观点",
                        evidence="",
                    ))
                else:
                    accuracy_passes += 1

        score = int((accuracy_passes / max(accuracy_checks, 1)) * 100)
        return min(score, 100), issues

    def _check_attribution(
        self, output: dict, source: dict
    ) -> tuple[int, list[CalibrationIssue]]:
        """
        维度2：归因正确性。
        检查评分理由是否有具体引用，而非空洞评价。
        """
        issues = []
        resume_text = source.get("resume_text", "")
        jd_text = source.get("jd_text", "")
        all_text = resume_text + " " + jd_text

        # 检查 matched_points 和 gap_points
        points_to_check = []
        for key in ["matched_points", "gap_points", "risk_points"]:
            for i, point in enumerate(output.get(key, [])):
                if isinstance(point, dict):
                    reason = point.get("reason", "") or point.get("point", "")
                else:
                    reason = str(point)
                points_to_check.append((key, i, reason))

        # 空洞评价的模式
        vague_patterns = [
            r"技术能力强", r"经验丰富", r"综合素质好", r"能力突出",
            r"表现优秀", r"基础扎实", r"沟通能力强", r"学习能力强",
        ]

        empty_attributions = 0
        for key, idx, reason in points_to_check:
            if not reason:
                continue

            is_vague = any(re.search(p, reason) for p in vague_patterns)
            has_quote = '"' in reason or "「" in reason or "'" in reason
            has_specific = any(
                indicator in reason
                for indicator in ["年", "项目", "公司", "学校", "负责", "使用", "完成", "实现"]
            )

            if is_vague and not has_quote:
                empty_attributions += 1
                issues.append(CalibrationIssue(
                    dimension="归因正确性",
                    severity=Severity.MAJOR,
                    location=f"{key}[{idx}]",
                    description=f"评分理由空洞，缺少具体引用: '{reason[:60]}'",
                    suggested_fix=f"请引用简历/JD中的具体原文来支撑此评分理由",
                    evidence="",
                ))

        total = max(len(points_to_check), 1)
        score = int(((total - empty_attributions) / total) * 100)
        return score, issues

    def _check_format_compliance(
        self, output: dict, output_type: str
    ) -> tuple[int, list[CalibrationIssue]]:
        """
        维度3：格式合规。
        检查输出是否符合约定的JSON Schema。
        """
        issues = []
        schema = OUTPUT_SCHEMAS.get(output_type, {})

        if not schema:
            # 无 schema 定义 → 只做基本检查
            return 100, []

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        total_checks = len(required) + len(properties)
        passed_checks = total_checks

        # 检查 required 字段
        for field in required:
            if field not in output or output[field] is None:
                passed_checks -= 1
                issues.append(CalibrationIssue(
                    dimension="格式合规",
                    severity=Severity.CRITICAL,
                    location=f"output.{field}",
                    description=f"缺少必填字段: {field}",
                    suggested_fix=f"请确保输出中包含 {field} 字段",
                ))

        # 检查字段类型和范围
        for field, props in properties.items():
            if field not in output or output[field] is None:
                continue
            val = output[field]
            expected_type = props.get("type")

            if expected_type == "integer" and not isinstance(val, int):
                passed_checks -= 1
                issues.append(CalibrationIssue(
                    dimension="格式合规",
                    severity=Severity.CRITICAL,
                    location=f"output.{field}",
                    description=f"字段 {field} 应为整数，实际为 {type(val).__name__}",
                    suggested_fix=f"请将 {field} 改为整数值",
                ))

            if expected_type == "array" and not isinstance(val, list):
                passed_checks -= 1
                issues.append(CalibrationIssue(
                    dimension="格式合规",
                    severity=Severity.CRITICAL,
                    location=f"output.{field}",
                    description=f"字段 {field} 应为数组",
                    suggested_fix=f"请将 {field} 改为数组格式",
                ))

            # 数值范围
            if "minimum" in props and isinstance(val, (int, float)) and val < props["minimum"]:
                passed_checks -= 1
                issues.append(CalibrationIssue(
                    dimension="格式合规",
                    severity=Severity.MAJOR,
                    location=f"output.{field}",
                    description=f"字段 {field} 的值 {val} 小于最小值 {props['minimum']}",
                    suggested_fix=f"请调整 {field} 的值使其 ≥ {props['minimum']}",
                ))

            if "maximum" in props and isinstance(val, (int, float)) and val > props["maximum"]:
                passed_checks -= 1
                issues.append(CalibrationIssue(
                    dimension="格式合规",
                    severity=Severity.MAJOR,
                    location=f"output.{field}",
                    description=f"字段 {field} 的值 {val} 大于最大值 {props['maximum']}",
                    suggested_fix=f"请调整 {field} 的值使其 ≤ {props['maximum']}",
                ))

        score = int((passed_checks / max(total_checks, 1)) * 100)
        return score, issues

    def _check_dimension_coverage(
        self, output: dict
    ) -> tuple[int, list[CalibrationIssue]]:
        """
        维度4：维度覆盖。
        检查面试题是否覆盖全部5个维度。
        """
        issues = []
        questions = output.get("questions", [])

        if not questions:
            return 0, [CalibrationIssue(
                dimension="维度覆盖",
                severity=Severity.CRITICAL,
                location="output.questions",
                description="面试题列表为空",
                suggested_fix="请生成至少10道面试题",
            )]

        # 统计覆盖的维度
        covered = set()
        for q in questions:
            cat = q.get("category", "")
            if cat in REQUIRED_DIMENSIONS:
                covered.add(cat)

        missing = set(REQUIRED_DIMENSIONS) - covered

        for dim in missing:
            issues.append(CalibrationIssue(
                dimension="维度覆盖",
                severity=Severity.MAJOR,
                location="questions[].category",
                description=f"缺少'{dim}'维度的面试题，当前仅覆盖 {len(covered)}/5 维度",
                suggested_fix=f"请为候选人的简历内容生成2-3道'{dim}'维度的面试题",
            ))

        score = int((len(covered) / len(REQUIRED_DIMENSIONS)) * 100)
        return score, issues

    def _check_hallucination(
        self, output: dict, source: dict
    ) -> tuple[int, list[CalibrationIssue]]:
        """
        维度5：幻觉检测。
        检查输出中是否有简历/JD中不存在的信息。
        """
        issues = []
        resume_text = source.get("resume_text", "")
        jd_text = source.get("jd_text", "")
        all_text_lower = (resume_text + " " + jd_text).lower()

        # 常见幻觉模式：编造奖项、公司、学校等
        hallucination_patterns = [
            (r"(获得|荣获|曾获)([\u4e00-\u9fff]+奖)", "奖项"),
            (r"(ACM|ICPC|Kaggle|NeurIPS|ICML|CVPR)", "竞赛/会议"),
            (r"(在\s*[\u4e00-\u9fff]+公司\s*(实习|工作|任职))", "公司经历"),
        ]

        for pattern, label in hallucination_patterns:
            for match in re.finditer(pattern, str(output)):
                matched_text = match.group()
                if matched_text.lower() not in all_text_lower:
                    issues.append(CalibrationIssue(
                        dimension="幻觉检测",
                        severity=Severity.CRITICAL,
                        location="output",
                        description=f"检测到可能的幻觉: '{matched_text}' (类型: {label})，该信息在简历和JD中均未找到",
                        suggested_fix=f"请删除编造的{label}信息，仅基于简历和JD的实际内容进行分析",
                        evidence=matched_text,
                    ))

        score = 100 - min(len(issues) * 15, 100)
        return max(score, 0), issues

    # ── 修订闭环 ────────────────────────────────────
    #
    # 这里曾有一个 run_calibration_loop，已删除。留这段说明是为了防止它被重建：
    #
    #   · 它从未被任何地方调用过（全仓 grep 只有定义处一处），
    #     真正在跑的闭环是 pipeline.py 的 _run_checker_loop。
    #   · 它带一个不查就看不出来的 bug：三轮未过时 `return agent_output`
    #     交的是**最后一轮**。而模型按反馈改 A 问题时把 B 改坏很常见，
    #     实测轨迹 75→87→80 里最后一轮就不是最好的那一轮。
    #     pipeline 那版按加权分择优（best_output/best_score），是对的。
    #
    # 所以它不是"少调用了的好实现"，而是一个更像正统实现、位置更显眼、
    # 却会把结果改坏的陷阱。要改校准循环，请改 pipeline.py::_run_checker_loop。

    # ── 辅助方法 ────────────────────────────────────

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词"""
        if not text:
            return []
        # 简单分词：提取中文词和英文词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', text)
        # 去重、去停用词
        stopwords = {"的", "了", "在", "是", "有", "和", "就", "不", "人", "都", "一", "一个",
                     "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看",
                     "好", "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "the", "a", "an",
                     "is", "are", "was", "were", "be", "been", "has", "have", "had", "do", "does"}
        return [w for w in words if w.lower() not in stopwords]

    def _generate_summary(
        self, scores: dict, issues: list[CalibrationIssue], passed: bool
    ) -> str:
        """生成校验摘要"""
        parts = [f"校验结果: {'✅ 通过' if passed else '❌ 未通过'}"]
        for dim, score in scores.items():
            threshold = CALIBRATION_DIMENSIONS[dim]["pass_threshold"]
            icon = "✅" if score >= threshold else "❌"
            parts.append(f"  {icon} {dim}: {score}/100 (阈值: {threshold})")

        if issues:
            parts.append(f"\n共发现 {len(issues)} 个问题:")
            for issue in issues[:5]:
                parts.append(f"  [{issue.severity.value}] {issue.dimension}: {issue.description[:80]}")

        return "\n".join(parts)

    def format_feedback_for_display(self, result: CheckerResult) -> str:
        """将 CheckerResult 格式化为前端可展示的文本"""
        return result.summary

    def to_dict(self, result: CheckerResult) -> dict:
        """序列化为 dict（供前端展示）"""
        return {
            "verdict": result.verdict,
            "calibration_scores": result.calibration_scores,
            "skipped_dimensions": result.skipped_dimensions,
            "weighted_score": result.weighted_score,
            "overall_pass": result.overall_pass,
            "revision_round": result.revision_round,
            "summary": result.summary,
            "issues": [
                {
                    "dimension": i.dimension,
                    "severity": i.severity.value,
                    "location": i.location,
                    "description": i.description,
                    "suggested_fix": i.suggested_fix,
                }
                for i in result.issues
            ],
        }
