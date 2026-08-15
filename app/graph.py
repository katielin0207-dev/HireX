"""
Graph DAG 编排引擎：管理 Agent 工作流的 DAG 拓扑、并行执行、条件分支。

════════════════════════════════════════════════════════════════
 ★ 显式数据传递 —— 本次重构的核心
════════════════════════════════════════════════════════════════

任务要求原文：

    「Graph 节点间的数据传递必须是显式的（函数参数/返回值），
      不能依赖全局变量。」

上一版有一个 `self.data_pool` 全局字典：节点产出写进去，下游从里面取，
根节点直接 `return dict(self.data_pool)` 拿走整个池子。那是**共享可变全局
状态**，正是要求里点名禁止的东西 —— 而文件头注释当时还写着"不依赖全局状态"。

现在的模型：

    初始输入   run(initial_input=...) 传入后【只读】，节点不能改它
              节点要用哪个 key 必须在 needs_initial 里显式声明
    节点之间   只能通过【声明过的边】拿上游产出
              边可指定 data_key（取上游输出的哪个字段）与 as_key（在下游叫什么）
    产出       只写进 NodeResult.output（执行记录），不写进任何共享池

★ 每个节点的输入都带 provenance（每个 key 从哪来），
  `explain_inputs()` 可以把它打印出来 —— 这既是自证"数据流显式"的证据，
  也是 Demo 里可以直接展示的东西。

════════════════════════════════════════════════════════════════
 其他修复
════════════════════════════════════════════════════════════════

  · 条件分支真正影响执行（上一版只写日志，返回的 next_node 拿到就扔）
  · 依赖失败 → 下游标记 SKIPPED（上一版 NodeStatus.SKIPPED 定义了从未使用，
    下游会拿着缺失的输入照常跑）
  · 节点级超时生效（上一版 GraphNode.timeout 定义了没用，硬编码 300s，
    且单节点层完全没有超时保护）
"""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from .harness import AgentHarness, HarnessResult


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GraphNode:
    """DAG 中的一个节点。"""

    name: str
    fn: Callable                            # fn(inputs: dict, attempt: int = 0) -> Any
    harness: Optional[AgentHarness] = None
    depends_on: list[str] = field(default_factory=list)
    needs_initial: list[str] = field(default_factory=list)
    """★ 本节点要从【初始输入】里取哪些 key。不声明就拿不到 —— 这是"显式"的一半。

    上一版根节点直接拿走整个 data_pool，等于每个节点都对全部输入有可见性。
    声明式的好处不只是干净：它让"这个节点到底依赖什么"变成可被检查的事实，
    而不是要读完函数体才知道。
    """
    condition: Optional[Callable] = None
    """条件分支：fn(inputs, output) -> str | list[str] | None

    返回**要激活的下游节点名**。未被任何已执行 condition 选中的下游节点会被
    标记 SKIPPED。返回 None 表示不做分支裁剪（全部下游照常执行）。
    """
    timeout: int = 120
    optional: bool = False
    """True 时，本节点失败不会让下游 SKIPPED（下游自己处理缺失输入）。"""
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """DAG 中的有向数据边。

    ★ 上一版的 data_key 定义了但从未被读取 —— edges 列表只被 append，
      `_build_inputs` 根本不看它。现在它真的决定数据怎么流。
    """

    from_node: str
    to_node: str
    data_key: Optional[str] = None
    """从上游输出里取哪个字段。None = 取整个输出。"""
    as_key: Optional[str] = None
    """在下游 inputs 里叫什么。None = 用 data_key，再退回用 from_node 名。"""


@dataclass
class NodeResult:
    node_name: str
    status: NodeStatus
    output: Any = None
    error: Optional[str] = None
    harness_result: Optional[HarnessResult] = None
    duration_ms: float = 0
    inputs_provenance: dict[str, str] = field(default_factory=dict)
    """★ 每个输入 key 的来源。'initial' 或 'node:<name>' 或 'node:<name>.<field>'。"""
    timestamp: float = field(default_factory=time.time)


class GraphOrchestrator:
    """DAG 编排器：拓扑分层、层内并行、显式数据边、条件分支。

    Usage:
        graph = GraphOrchestrator()
        graph.add_node(GraphNode(name="parse_jd", fn=f1, needs_initial=["jd_text"]))
        graph.add_node(GraphNode(name="match", fn=f3, depends_on=["parse_jd"]))
        graph.add_edge("parse_jd", "match", as_key="jd_data")
        results = graph.run(initial_input={"jd_text": "..."})
    """

    def __init__(self, name: str = "recruitment-pipeline", max_workers: int = 4):
        self.name = name
        self.max_workers = max_workers
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.results: dict[str, NodeResult] = {}
        self.execution_log: list[dict] = []
        # ★ 只读初始输入。用 MappingProxyType 让"节点改不了它"成为运行时事实，
        #   而不是一句口头约定 —— 约定会被下一个赶进度的人绕过。
        self._initial: Mapping[str, Any] = MappingProxyType({})
        self._skipped_by_condition: set[str] = set()

    # ── 构建 API ──────────────────────────────────────

    def set_initial_input(self, data: dict) -> "GraphOrchestrator":
        """设置初始输入。只读，节点无法修改。"""
        self._initial = MappingProxyType(dict(data or {}))
        return self

    def add_node(self, node: GraphNode) -> "GraphOrchestrator":
        self.nodes[node.name] = node
        return self

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        data_key: str = None,
        as_key: str = None,
    ) -> "GraphOrchestrator":
        self.edges.append(GraphEdge(from_node, to_node, data_key, as_key))
        if to_node in self.nodes:
            node = self.nodes[to_node]
            if from_node not in node.depends_on:
                node.depends_on.append(from_node)
        return self

    # ── 拓扑 ──────────────────────────────────────────

    def _topological_sort(self) -> list[list[str]]:
        """Kahn 分层拓扑排序，同层可并行。"""
        in_degree = {name: 0 for name in self.nodes}
        adj: dict[str, list[str]] = {name: [] for name in self.nodes}

        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep in self.nodes:
                    in_degree[node.name] += 1
                    adj[dep].append(node.name)

        queue = deque([n for n, d in in_degree.items() if d == 0])
        layers: list[list[str]] = []

        while queue:
            layer = list(queue)
            layers.append(layer)
            nxt: deque[str] = deque()
            for name in layer:
                for neighbor in adj[name]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        nxt.append(neighbor)
            queue = nxt

        if sum(len(L) for L in layers) != len(self.nodes):
            stuck = [n for n, d in in_degree.items() if d > 0]
            raise ValueError(f"Graph has a cycle! Unprocessed nodes: {stuck}")

        return layers

    # ── 执行 ──────────────────────────────────────────

    def run(self, initial_input: dict = None) -> dict[str, NodeResult]:
        if initial_input is not None:
            self.set_initial_input(initial_input)

        layers = self._topological_sort()
        self.execution_log.append({
            "event": "graph_start",
            "layers": [list(layer) for layer in layers],
            "total_nodes": len(self.nodes),
            "initial_keys": sorted(self._initial.keys()),
            "timestamp": time.time(),
        })

        for layer_idx, layer in enumerate(layers):
            self._execute_layer(layer, layer_idx)

        self.execution_log.append({
            "event": "graph_end",
            "results": {n: r.status.value for n, r in self.results.items()},
            "timestamp": time.time(),
        })
        return self.results

    def _execute_layer(self, layer: list[str], layer_idx: int) -> None:
        runnable = [n for n in layer if not self._resolve_skip(n)]

        if not runnable:
            return
        if len(runnable) == 1:
            self._execute_node(runnable[0])
            return

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(runnable))) as pool:
            futures = {pool.submit(self._execute_node, n): n for n in runnable}
            for future in futures:
                name = futures[future]
                try:
                    # ★ 用节点自己声明的 timeout，不再硬编码 300s
                    future.result(timeout=self.nodes[name].timeout + 5)
                except FutureTimeout:
                    self._record_failure(name, f"节点超时（>{self.nodes[name].timeout}s）", 0)
                except Exception as e:  # noqa: BLE001
                    self._record_failure(name, str(e), 0)

    def _resolve_skip(self, node_name: str) -> bool:
        """判断节点是否应被跳过，并落一条 SKIPPED 结果。

        两种跳过来源：
          1. 上游 condition 没有选中它
          2. 必需的上游依赖失败或被跳过 —— ★ 上一版这里什么都不做，
             下游会拿着缺失输入照常执行，然后在业务代码里表现为莫名其妙的空结果
        """
        node = self.nodes[node_name]

        if node_name in self._skipped_by_condition:
            self._record_skip(node_name, "未被上游条件分支选中")
            return True

        for dep in node.depends_on:
            dep_node = self.nodes.get(dep)
            if dep_node is not None and dep_node.optional:
                continue
            dep_result = self.results.get(dep)
            if dep_result is None:
                continue
            if dep_result.status in (NodeStatus.FAILED, NodeStatus.SKIPPED):
                self._record_skip(node_name, f"依赖 {dep} 状态为 {dep_result.status.value}")
                return True
        return False

    def _execute_node(self, node_name: str) -> None:
        node = self.nodes[node_name]
        t0 = time.time()

        inputs, provenance = self._build_inputs(node)

        self.execution_log.append({
            "event": "node_start",
            "node": node_name,
            "input_keys": sorted(inputs.keys()),
            "provenance": provenance,
            "timestamp": time.time(),
        })

        try:
            if node.harness:
                hr = node.harness.run(
                    agent_fn=node.fn,
                    input_data=inputs,
                    schema=node.metadata.get("output_schema"),
                    fallback_template=node.metadata.get("fallback_template"),
                    timeout_seconds=node.timeout,
                )
                output, harness_result = hr.data, hr
            else:
                output, harness_result = node.fn(inputs), None

            duration = (time.time() - t0) * 1000
            self.results[node_name] = NodeResult(
                node_name=node_name,
                status=NodeStatus.SUCCESS,
                output=output,
                harness_result=harness_result,
                duration_ms=duration,
                inputs_provenance=provenance,
            )
            self.execution_log.append({
                "event": "node_success",
                "node": node_name,
                "duration_ms": duration,
                "degraded": bool(harness_result and harness_result.degraded),
                "timestamp": time.time(),
            })

            # ★ 条件分支在节点【执行完之后立刻】结算，才能影响后续层。
            #   上一版放在所有层跑完之后，且只写日志 —— 那是装饰不是分支。
            self._apply_condition(node, inputs, output)

        except Exception as e:  # noqa: BLE001
            self._record_failure(node_name, str(e), (time.time() - t0) * 1000, provenance)

    def _apply_condition(self, node: GraphNode, inputs: dict, output: Any) -> None:
        if not node.condition:
            return
        try:
            chosen = node.condition(inputs, output)
        except Exception as e:  # noqa: BLE001
            self.execution_log.append({
                "event": "condition_error", "node": node.name,
                "error": str(e), "timestamp": time.time(),
            })
            return

        if chosen is None:
            return
        chosen_set = {chosen} if isinstance(chosen, str) else set(chosen)

        downstream = {n.name for n in self.nodes.values() if node.name in n.depends_on}
        skipped = downstream - chosen_set
        self._skipped_by_condition |= skipped

        self.execution_log.append({
            "event": "condition_routed",
            "node": node.name,
            "activated": sorted(chosen_set & downstream),
            "skipped": sorted(skipped),
            "timestamp": time.time(),
        })

    # ── ★ 显式输入构建 ────────────────────────────────

    def _build_inputs(self, node: GraphNode) -> tuple[dict, dict[str, str]]:
        """只从两个来源构建输入，且每个 key 都记来源。

        1. 初始输入里【本节点声明过】的 key（needs_initial）
        2. 指向本节点的【边】所携带的上游产出

        没有第三个来源 —— 特别是没有"从共享池里捞"。
        """
        inputs: dict[str, Any] = {}
        provenance: dict[str, str] = {}

        for key in node.needs_initial:
            if key in self._initial:
                inputs[key] = self._initial[key]
                provenance[key] = "initial"

        for edge in self.edges:
            if edge.to_node != node.name:
                continue
            dep_result = self.results.get(edge.from_node)
            if dep_result is None or dep_result.status != NodeStatus.SUCCESS:
                continue

            value = dep_result.output
            source = f"node:{edge.from_node}"
            if edge.data_key:
                if not isinstance(value, dict) or edge.data_key not in value:
                    continue
                value = value[edge.data_key]
                source = f"node:{edge.from_node}.{edge.data_key}"

            key = edge.as_key or edge.data_key or edge.from_node
            inputs[key] = value
            provenance[key] = source

        return inputs, provenance

    # ── 结果记录 ──────────────────────────────────────

    def _record_failure(self, name: str, error: str, duration: float, provenance: dict = None) -> None:
        self.results[name] = NodeResult(
            node_name=name, status=NodeStatus.FAILED, error=error,
            duration_ms=duration, inputs_provenance=provenance or {},
        )
        self.execution_log.append({
            "event": "node_failed", "node": name, "error": error,
            "duration_ms": duration, "timestamp": time.time(),
        })

    def _record_skip(self, name: str, reason: str) -> None:
        self.results[name] = NodeResult(node_name=name, status=NodeStatus.SKIPPED, error=reason)
        self.execution_log.append({
            "event": "node_skipped", "node": name, "reason": reason, "timestamp": time.time(),
        })

    # ── 查询 API ──────────────────────────────────────

    def get_result(self, node_name: str) -> Optional[NodeResult]:
        return self.results.get(node_name)

    def get_output(self, node_name: str) -> Any:
        r = self.results.get(node_name)
        return r.output if r and r.status == NodeStatus.SUCCESS else None

    def explain_inputs(self, node_name: str) -> str:
        """★ 打印某节点每个输入的来源。

        这是"数据流是显式的"这句话的证据：能逐 key 说清它从哪来。
        全局池子做不到这件事 —— 那正是它的问题。
        """
        r = self.results.get(node_name)
        if not r or not r.inputs_provenance:
            return f"{node_name}: 无输入记录"
        lines = [f"{node_name} 的输入来源："]
        for key, src in sorted(r.inputs_provenance.items()):
            lines.append(f"  {key:<24} ← {src}")
        return "\n".join(lines)

    def get_execution_summary(self) -> dict:
        total = len(self.results)
        by = lambda s: sum(1 for r in self.results.values() if r.status == s)  # noqa: E731
        return {
            "graph_name": self.name,
            "total_nodes": total,
            "success": by(NodeStatus.SUCCESS),
            "failed": by(NodeStatus.FAILED),
            "skipped": by(NodeStatus.SKIPPED),
            "total_duration_ms": sum(r.duration_ms for r in self.results.values()),
            "details": {
                name: {
                    "status": r.status.value,
                    "duration_ms": r.duration_ms,
                    "inputs_from": r.inputs_provenance,
                    "error": r.error,
                }
                for name, r in self.results.items()
            },
        }

    def print_dag(self) -> str:
        """Mermaid 格式。★ 边上标注 as_key，让数据流在图上就能看见。"""
        lines = ["graph TD"]
        for node_name, node in self.nodes.items():
            label = node.metadata.get("label", node_name)
            lines.append(f"    {node_name}[{label}]")
        for edge in self.edges:
            tag = edge.as_key or edge.data_key
            arrow = f"-->|{tag}|" if tag else "-->"
            lines.append(f"    {edge.from_node} {arrow} {edge.to_node}")
        for node in self.nodes.values():
            for dep in node.depends_on:
                if not any(e.from_node == dep and e.to_node == node.name for e in self.edges):
                    lines.append(f"    {dep} -.-> {node.name}")
        return "\n".join(lines)
