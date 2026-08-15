
"""
Agent Harness 执行护栏：为每个 Agent 提供输入/输出校验、降级策略、重试机制。

五级降级链：
  Level 1: JSON 修复
  Level 2: 重新生成（降低temperature）
  Level 3: 模板兜底
  Level 4: 降级输出（标记 degraded:true）
  Level 5: 硬失败（抛出异常）
"""

from __future__ import annotations
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class FallbackLevel(Enum):
    """降级级别"""
    JSON_FIX = 1        # JSON修复
    REGENERATE = 2      # 重新生成
    TEMPLATE = 3        # 模板兜底
    DEGRADED = 4        # 降级输出
    HARD_FAIL = 5       # 硬失败


@dataclass
class ValidationError:
    """校验错误"""
    field: str
    message: str
    severity: str = "error"  # error | warning
    expected: Any = None
    actual: Any = None


@dataclass
class HarnessResult:
    """Harness 执行结果"""
    data: Any                           # 最终输出数据
    passed: bool = True                 # 是否通过所有校验
    errors: list[ValidationError] = field(default_factory=list)
    degraded: bool = False              # 是否降级输出
    fallback_level: Optional[FallbackLevel] = None
    attempts: int = 1
    total_duration_ms: float = 0
    logs: list[str] = field(default_factory=list)


@dataclass
class HarnessConfig:
    """Harness 配置"""
    max_retries: int = 3
    timeout_seconds: int = 90
    temperature: float = 0.3
    temperature_fallback: float = 0.1    # 降级时使用的温度
    max_tokens: int = 8192
    enable_metrics: bool = True
    backoff_base: float = 1.0            # 指数退避基数（秒）
    backoff_cap: float = 8.0             # 退避上限，避免第三次重试等太久


class AgentHarness:
    """
    Agent 执行护栏。

    Usage:
        harness = AgentHarness(config=HarnessConfig(max_retries=3))

        def my_agent(inputs: dict, attempt: int = 0) -> dict:
            # attempt 可用于调整行为（如降低temperature）
            ...

        result = harness.run(
            agent_fn=my_agent,
            input_data={"jd_text": "...", "resume_text": "..."},
            schema={"type": "object", "required": ["overall_score", "questions"]},
            fallback_template=default_output_template,
        )
    """

    def __init__(self, config: HarnessConfig = None, agent_name: str = "agent"):
        self.config = config or HarnessConfig()
        self.agent_name = agent_name
        self.metrics: list[dict] = []  # 执行指标

    def run(
        self,
        agent_fn: Callable,
        input_data: dict,
        schema: dict = None,
        fallback_template: Any = None,
        timeout_seconds: int = None,
    ) -> HarnessResult:
        """
        执行 Agent 并应用完整 Harness 保护。

        Args:
            agent_fn: Agent 执行函数 fn(inputs, attempt) -> output
            input_data: 输入数据
            schema: 期望的 JSON Schema（用于输出校验）
            fallback_template: 兜底模板（Level 3 使用）
            timeout_seconds: 单次尝试的超时；None 则用 config.timeout_seconds

        Returns:
            HarnessResult: 包含最终数据和执行元信息
        """
        t0 = time.time()
        logs: list[str] = []
        input_data = dict(input_data or {})
        timeout = timeout_seconds or self.config.timeout_seconds

        # ── Phase 1: 输入校验 ──────────────────────
        validated_input = self._validate_input(input_data, schema)
        logs.append(f"[{self.agent_name}] Input validated: {len(input_data)} keys")

        last_output: Any = None
        last_errors: list[ValidationError] = []
        last_exc: str = ""      # 最后一次异常的原文，供硬失败时报出去
        attempt = 0

        for attempt in range(self.config.max_retries):
            # ★ 指数退避 —— 上一版直接 continue，等于把上游的限流/抖动原样打回去。
            #   要求原文写着「指数退避重试（最多3次）」，之前只做到了"重试"。
            if attempt > 0:
                backoff = min(self.config.backoff_base * (2 ** (attempt - 1)), self.config.backoff_cap)
                logs.append(f"[{self.agent_name}] Backoff {backoff:.1f}s before attempt {attempt + 1}")
                time.sleep(backoff)

            attempt_t0 = time.time()
            try:
                # ── Phase 2: 执行 Agent（带超时）──────
                logs.append(f"[{self.agent_name}] Attempt {attempt + 1}/{self.config.max_retries}")
                # ★ temperature 真的传下去了。上一版定义了 temperature_fallback
                #   却从未传给 agent_fn —— "降低 temperature 重新生成"这级降级
                #   实际上从来没有生效过。
                temperature = self.config.temperature if attempt == 0 else self.config.temperature_fallback
                validated_input["_temperature"] = temperature
                validated_input["_attempt"] = attempt

                output = self._call_with_timeout(agent_fn, validated_input, attempt, timeout)
                last_output = output

                # ── Phase 3: 输出校验 ────────────────
                if not schema:
                    self._record_attempt(attempt, attempt_t0, True, "no_schema")
                    return self._ok(output, attempt, t0, logs)

                errors = self._validate_output(output, schema)
                if not errors:
                    logs.append(f"[{self.agent_name}] Output passed validation")
                    self._record_attempt(attempt, attempt_t0, True, "passed")
                    return self._ok(output, attempt, t0, logs)

                last_errors = errors
                logs.append(f"[{self.agent_name}] Output failed: {len(errors)} errors")
                self._record_attempt(attempt, attempt_t0, False, f"{len(errors)} validation errors")

                # Level 1: JSON 修复
                fixed = self._try_json_fix(output, schema)
                if fixed is not None and not self._validate_output(fixed, schema):
                    logs.append(f"[{self.agent_name}] Level 1: JSON fix succeeded")
                    return self._ok(fixed, attempt, t0, logs, fallback_level=FallbackLevel.JSON_FIX)

                # Level 2: 携带错误信息重新生成（下一轮 temperature 已降低）
                if attempt < self.config.max_retries - 1:
                    logs.append(f"[{self.agent_name}] Level 2: Regenerate at lower temperature")
                    validated_input["_fallback"] = True
                    validated_input["_errors"] = [e.message for e in errors]
                    continue

            except TimeoutError as e:
                logs.append(f"[{self.agent_name}] Timeout: {e}")
                last_exc = f"Timeout: {e}"
                self._record_attempt(attempt, attempt_t0, False, "timeout")
            except Exception as e:  # noqa: BLE001
                logs.append(f"[{self.agent_name}] Exception: {e}")
                last_exc = f"{type(e).__name__}: {e}"
                self._record_attempt(attempt, attempt_t0, False, type(e).__name__)

        # ── Phase 4: 降级策略 ──────────────────────
        # Level 3: 模板兜底
        if fallback_template is not None:
            logs.append(f"[{self.agent_name}] Level 3: Template fallback")
            return HarnessResult(
                data=fallback_template, passed=False, degraded=True,
                fallback_level=FallbackLevel.TEMPLATE,
                errors=[ValidationError("output", "Used template fallback")],
                attempts=attempt + 1,
                total_duration_ms=(time.time() - t0) * 1000, logs=logs,
            )

        # ★ Level 4: 降级输出 —— 上一版**完全没有这一级**，从 Level 3 直接跳到
        #   硬失败（注释里写的是"Level 4-5: 硬失败"，把两级合并了）。
        #   五级降级链因此实际只有四级。
        #   有部分可用字段时，返回它 + errors，标记 degraded，让上层自己决定
        #   够不够用 —— 而不是把已经拿到的东西全扔掉再抛异常。
        if isinstance(last_output, dict) and last_output:
            partial = {k: v for k, v in last_output.items() if v is not None}
            logs.append(
                f"[{self.agent_name}] Level 4: Degraded output "
                f"({len(partial)} usable fields, {len(last_errors)} errors)"
            )
            return HarnessResult(
                data={**partial, "degraded": True},
                passed=False, degraded=True,
                fallback_level=FallbackLevel.DEGRADED,
                errors=last_errors or [ValidationError("output", "Degraded partial output")],
                attempts=attempt + 1,
                total_duration_ms=(time.time() - t0) * 1000, logs=logs,
            )

        # Level 5: 硬失败
        logs.append(f"[{self.agent_name}] Level 5: Hard fail after {attempt + 1} attempts")
        self.record_metric({
            "event": "hard_fail", "attempts": attempt + 1,
            "duration_ms": (time.time() - t0) * 1000,
        })
        raise RuntimeError(
            f"[{self.agent_name}] Failed after {self.config.max_retries} attempts. "
            # ★ 上一版这里用的是一个永远为 None 的变量，所以永远打印 'N/A'
            f"Last output: {str(last_output)[:200] if last_output is not None else 'N/A'}"
            # ★ 异常从来没有被带出来 —— 三次都抛异常时 last_output 就是 None，
            #   于是错误信息只剩一句 'Last output: N/A'，看不出到底是超时、
            #   限流、还是 Schema 不合格。真正的原因只留在 logs 里没人看。
            + (f" | Last error: {last_exc}" if last_exc else "")
        )

    # ── 执行与计时 ──────────────────────────────────

    def _call_with_timeout(self, agent_fn: Callable, inputs: dict, attempt: int, timeout: int) -> Any:
        """★ 真正的超时控制。

        上一版 HarnessConfig.timeout_seconds=90 定义了，但 run() 里没有任何
        超时逻辑 —— 一个卡住的模型调用会把整条流水线挂死，而要求里明确写着
        「超时控制（默认90s）」。
        """
        # ⚠️ 不能用 `with ThreadPoolExecutor(...)`：
        #    with 退出时会 shutdown(wait=True)，**阻塞到工作线程自然结束** ——
        #    于是 future.result(timeout=1) 抛了超时，程序却还是等满了 5 秒，
        #    超时形同虚设。这个坑是冒烟测试抓出来的（第一版实测「1s 超时」
        #    的调用整整跑了 5.0s 才返回）。
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(agent_fn, inputs, attempt=attempt)
            try:
                result = future.result(timeout=timeout)
            except FutureTimeout as e:
                raise TimeoutError(f"agent 执行超过 {timeout}s") from e
            pool.shutdown(wait=False)
            return result
        except BaseException:
            # ★ 说实话：Python 杀不掉运行中的线程。这里只做到「调用方不再被卡住」，
            #   那个超时的请求会在后台自己跑完再消失。对 LLM 调用来说这是可接受的
            #   ——真正的取消要靠底层 HTTP client 的 timeout，见 llm_client。
            #   写清楚是为了别让人误以为它被取消了。
            pool.shutdown(wait=False)
            raise

    def _ok(self, data: Any, attempt: int, t0: float, logs: list,
            fallback_level: FallbackLevel = None) -> HarnessResult:
        return HarnessResult(
            data=data, passed=True, attempts=attempt + 1,
            fallback_level=fallback_level,
            total_duration_ms=(time.time() - t0) * 1000, logs=logs,
        )

    def _record_attempt(self, attempt: int, t0: float, ok: bool, note: str) -> None:
        """★ 可观测性真的落地了。

        上一版 record_metric() 存在，但 run() 从不调用它 —— metrics 永远是空列表，
        get_metrics_summary() 永远返回 {}。要求里写的「每步耗时、成功率」全是空的。
        """
        self.record_metric({
            "event": "attempt", "attempt": attempt + 1,
            "duration_ms": (time.time() - t0) * 1000,
            "ok": ok, "note": note,
        })

    # ── 输入校验 ────────────────────────────────────

    def _validate_input(self, input_data: dict, schema: dict = None) -> dict:
        """校验输入数据"""
        if not isinstance(input_data, dict):
            raise ValueError(f"[{self.agent_name}] Input must be a dict, got {type(input_data)}")

        if schema and "required" in schema:
            for field in schema["required"]:
                # 以 "input." 前缀标记输入字段
                if field.startswith("input."):
                    key = field.replace("input.", "")
                    if key not in input_data or input_data[key] is None:
                        raise ValueError(f"[{self.agent_name}] Missing required input: {key}")

        return input_data

    # ── 输出校验 ────────────────────────────────────

    def _validate_output(self, output: Any, schema: dict) -> list[ValidationError]:
        """校验输出数据是否符合 Schema"""
        errors = []

        if not isinstance(output, dict):
            return [ValidationError(field="root", message=f"Output must be dict, got {type(output).__name__}")]

        # 检查 required 字段
        if "required" in schema:
            for field in schema["required"]:
                if field not in output or output[field] is None:
                    errors.append(ValidationError(
                        field=field,
                        message=f"Missing required field: {field}",
                        severity="error",
                    ))

        # 检查 properties 类型
        if "properties" in schema:
            for field, props in schema["properties"].items():
                if field in output and output[field] is not None:
                    expected_type = props.get("type")
                    if expected_type == "integer":
                        if not isinstance(output[field], int):
                            errors.append(ValidationError(
                                field=field,
                                message=f"Expected int, got {type(output[field]).__name__}",
                                expected="int",
                                actual=type(output[field]).__name__,
                            ))
                    elif expected_type == "number":
                        if not isinstance(output[field], (int, float)):
                            errors.append(ValidationError(
                                field=field,
                                message=f"Expected number, got {type(output[field]).__name__}",
                            ))
                    elif expected_type == "array":
                        if not isinstance(output[field], list):
                            errors.append(ValidationError(
                                field=field,
                                message=f"Expected array, got {type(output[field]).__name__}",
                            ))
                    elif expected_type == "string":
                        if not isinstance(output[field], str):
                            errors.append(ValidationError(
                                field=field,
                                message=f"Expected string, got {type(output[field]).__name__}",
                            ))

                    # 数值范围检查
                    if "minimum" in props and isinstance(output[field], (int, float)):
                        if output[field] < props["minimum"]:
                            errors.append(ValidationError(
                                field=field,
                                message=f"Value {output[field]} < minimum {props['minimum']}",
                            ))
                    if "maximum" in props and isinstance(output[field], (int, float)):
                        if output[field] > props["maximum"]:
                            errors.append(ValidationError(
                                field=field,
                                message=f"Value {output[field]} > maximum {props['maximum']}",
                            ))

        return errors

    # ── JSON 修复 ───────────────────────────────────

    def _try_json_fix(self, output: Any, schema: dict = None) -> Any:
        """
        Level 1: 尝试修复 JSON 输出。
        如果 output 是字符串，尝试提取和修复 JSON。
        """
        if not isinstance(output, str):
            return None

        text = output

        # 去除 Markdown 代码块标记
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = text.replace("```", "").strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 提取第一个 { } 或 [ ] 块
        for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
            match = re.search(pattern, text)
            if match:
                candidate = match.group()
                # 补全未闭合的括号和引号
                fixed = self._fix_brackets(candidate)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

        return None

    def _fix_brackets(self, text: str) -> str:
        """补全未闭合的括号和引号"""
        # 计算括号差
        brace_diff = text.count("{") - text.count("}")
        bracket_diff = text.count("[") - text.count("]")

        # 检查是否在字符串内
        in_string = False
        escape = False
        for ch in text:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string

        result = text
        if in_string:
            result += '"'
        result += "]" * max(0, bracket_diff)
        result += "}" * max(0, brace_diff)

        return result

    # ── 可观测性 ────────────────────────────────────

    def record_metric(self, metric: dict):
        """记录执行指标"""
        if self.config.enable_metrics:
            metric["agent"] = self.agent_name
            metric["timestamp"] = time.time()
            self.metrics.append(metric)

    def get_metrics_summary(self) -> dict:
        """指标摘要：调用次数、成功率、耗时分布。

        ★ 上一版只回 total_calls + 最近 5 条原始记录，而且因为 run() 从不调用
          record_metric，实际永远是 {}。要求里的「成功率、每步耗时」需要的是
          **聚合值**，不是原始流水 —— 原始流水看得见但用不了。
        """
        attempts = [m for m in self.metrics if m.get("event") == "attempt"]
        if not attempts:
            return {"agent": self.agent_name, "total_calls": 0}

        ok = sum(1 for m in attempts if m.get("ok"))
        durations = sorted(m.get("duration_ms", 0) for m in attempts)
        n = len(durations)
        return {
            "agent": self.agent_name,
            "total_attempts": n,
            "success_rate": round(ok / n, 3),
            "avg_duration_ms": round(sum(durations) / n, 1),
            "p95_duration_ms": round(durations[min(int(n * 0.95), n - 1)], 1),
            "hard_fails": sum(1 for m in self.metrics if m.get("event") == "hard_fail"),
            "failure_reasons": sorted({m.get("note", "") for m in attempts if not m.get("ok")} - {""}),
            "recent": self.metrics[-5:],
        }
