"""State machine — cyclic graph with conditional transitions. Accepts Agent objects."""
from __future__ import annotations
import asyncio
from typing import Any, Callable

class StateMachine:
    """Cyclic state graph with conditional transitions.
    
    Nodes can be Agent objects or functions.
    Agent objects are auto-wrapped: state["task"] → agent.run() → state updated.
    """
    def __init__(self, name: str = "state_machine", max_transitions: int = 50, cost_budget: float = 0):
        self.name = name
        self.nodes: dict[str, Callable] = {}
        self.transitions: list[tuple[str, str, Callable | None]] = []
        self.start_node: str | None = None
        self.end_nodes: set[str] = set()
        self.max_transitions = max_transitions
        self.cost_budget = cost_budget

    def add_node(self, name: str, handler: Any):
        self.nodes[name] = self._wrap_if_agent(handler, name)
        if not self.start_node: self.start_node = name

    def add_edge(self, source: str, target: str, condition: Callable | None = None):
        self.transitions.append((source, target, condition))

    def set_start(self, name: str): self.start_node = name
    def set_end(self, *names: str): self.end_nodes.update(names)

    async def run(self, initial_state: dict[str, Any] = None) -> dict[str, Any]:
        state = dict(initial_state or {})
        current = self.start_node
        step = 0; total_cost = 0.0

        while current and current not in self.end_nodes and step < self.max_transitions:
            if self.cost_budget > 0 and total_cost >= self.cost_budget:
                state["_budget_exceeded"] = True; break
            step += 1
            handler = self.nodes.get(current)
            if not handler: raise ValueError(f"Unknown node: {current}")
            if asyncio.iscoroutinefunction(handler):
                state = await handler(state) or state
            else:
                state = handler(state) or state
            state["_current_node"] = current; state["_step"] = step
            if hasattr(state.get(f"{current}_result"), "total_cost"):
                total_cost += state[f"{current}_result"].total_cost

            next_node = None
            for src, tgt, cond in self.transitions:
                if src == current:
                    if cond is None or cond(state): next_node = tgt; break
            current = next_node

        state["_final_node"] = current; state["_total_steps"] = step; state["_total_cost"] = total_cost
        return state

    def _wrap_if_agent(self, handler: Any, node_name: str) -> Callable:
        if hasattr(handler, 'run') and hasattr(handler, 'name') and hasattr(handler, 'instructions'):
            agent = handler
            async def _agent_handler(state: dict) -> dict:
                task = state.get(f"{node_name}_input") or state.get("task") or str(state)
                result = await agent.run(task)
                return {**state, f"{node_name}_output": result.content, f"{node_name}_result": result}
            return _agent_handler
        return handler
