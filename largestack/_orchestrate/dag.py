"""DAG workflow — accepts Agent objects OR functions. Auto-parallelizes independent nodes."""

from __future__ import annotations
import asyncio
from typing import Any, Callable


class DAGNode:
    def __init__(self, name: str, fn: Any, deps: list[str] = None):
        self.name = name
        self.fn = fn
        self.deps = deps or []


class DAGWorkflow:
    """Execute a directed acyclic graph with automatic parallelization.

    Nodes can be:
    - Agent objects: auto-wrapped to run with state["task"] or last output
    - async functions: called with (state: dict) -> dict
    - sync functions: called with (state: dict) -> dict
    """

    def __init__(self, name: str = "workflow", cost_budget: float = 0):
        self.name = name
        self.cost_budget = cost_budget
        self.nodes: dict[str, DAGNode] = {}

    def add_node(self, name: str, fn: Any, deps: list[str] = None):
        if name in self.nodes:
            raise ValueError(
                f"DAG already has a node named {name!r}. "
                f"Each node name must be unique. If you meant to update the "
                f"handler, remove and re-add the node, or use a different name."
            )
        # Auto-wrap Agent objects
        handler = self._wrap_if_agent(fn, name)
        self.nodes[name] = DAGNode(name, handler, deps or [])

    def add_edge(self, source: str, target: str, condition: Callable | None = None):
        if target in self.nodes:
            if source not in self.nodes[target].deps:
                self.nodes[target].deps.append(source)

    def _validate_graph(self) -> None:
        """Detect missing dependencies and cycles before execution.

        Raises ``ValueError`` with a clear message instead of silently
        producing an empty result.
        """
        # 1. Missing-dep check
        names = set(self.nodes.keys())
        for n in self.nodes.values():
            missing = [d for d in n.deps if d not in names]
            if missing:
                raise ValueError(
                    f"Node {n.name!r} depends on undefined node(s) "
                    f"{missing!r}. Add the dependency before run(), or "
                    f"remove it from deps=[]."
                )
        # 2. Cycle check via DFS with three colors
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}

        def visit(node_name: str, path: list[str]) -> None:
            color[node_name] = GRAY
            for dep in self.nodes[node_name].deps:
                if color[dep] == GRAY:
                    cycle = " → ".join(path + [node_name, dep])
                    raise ValueError(
                        f"Workflow has a dependency cycle: {cycle}. "
                        f"DAGs cannot contain cycles. Break the loop by "
                        f"removing a deps=[] entry or restructuring the flow."
                    )
                if color[dep] == WHITE:
                    visit(dep, path + [node_name])
            color[node_name] = BLACK

        for n in self.nodes:
            if color[n] == WHITE:
                visit(n, [])

    async def run(self, initial_state: dict[str, Any] = None) -> dict[str, Any]:
        # Validate before any execution — fail fast on graph errors.
        self._validate_graph()

        state = dict(initial_state or {})
        completed: set[str] = set()
        total_cost = 0.0

        while len(completed) < len(self.nodes):
            ready = [
                n
                for name, n in self.nodes.items()
                if name not in completed and all(d in completed for d in n.deps)
            ]
            if not ready:
                break

            # Cost budget check
            if self.cost_budget > 0 and total_cost >= self.cost_budget:
                state["_budget_exceeded"] = True
                break

            tasks = [self._exec_node(node, state) for node in ready]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    state[f"{node.name}_error"] = str(result)
                elif isinstance(result, dict):
                    state.update(result)
                else:
                    state[node.name] = result
                # v1.1.1: track cost. Agent-wrapped nodes return a dict carrying
                # ``{node}_cost``; a raw AgentResult/object exposes ``total_cost``.
                # The old ``hasattr(result, 'total_cost')`` was always False for the
                # dict case, so cost_budget never engaged.
                if isinstance(result, dict):
                    total_cost += float(result.get(f"{node.name}_cost", 0.0) or 0.0)
                elif hasattr(result, "total_cost"):
                    total_cost += float(getattr(result, "total_cost", 0.0) or 0.0)
                completed.add(node.name)

        state["_total_cost"] = total_cost
        return state

    async def _exec_node(self, node: DAGNode, state: dict) -> Any:
        if asyncio.iscoroutinefunction(node.fn):
            return await node.fn(state)
        return node.fn(state)

    def _wrap_if_agent(self, fn: Any, node_name: str) -> Callable:
        """Auto-wrap Agent objects into DAG-compatible handlers."""
        # Check if it's an Agent (duck typing to avoid circular import)
        if hasattr(fn, "run") and hasattr(fn, "name") and hasattr(fn, "instructions"):
            agent = fn

            async def _agent_handler(state: dict) -> dict:
                # Build prompt from state
                task = state.get(f"{node_name}_input") or state.get("task") or ""
                # Include outputs from dependency nodes
                dep_outputs = []
                for dep in self.nodes.get(node_name, DAGNode(node_name, None)).deps:
                    out = state.get(f"{dep}_output") or state.get(dep)
                    if out:
                        dep_outputs.append(f"[{dep}]: {out}" if isinstance(out, str) else str(out))
                if dep_outputs:
                    task = f"{task}\n\nPrevious results:\n" + "\n".join(dep_outputs)

                result = await agent.run(task)
                return {
                    **state,
                    f"{node_name}_output": result.content,
                    f"{node_name}_result": result,
                    f"{node_name}_cost": result.total_cost,
                }

            return _agent_handler
        return fn
