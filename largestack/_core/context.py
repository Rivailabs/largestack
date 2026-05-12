"""AgentContext — structured data passing between agents in workflows.

Replaces string-only context. Every agent gets full history of previous agents.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from largestack.types import AgentResult

class AgentContext(BaseModel):
    """Structured context passed between agents in multi-agent workflows."""
    task: str = ""
    outputs: dict[str, AgentResult] = Field(default_factory=dict)
    shared: dict[str, Any] = Field(default_factory=dict)
    total_cost: float = 0.0
    workflow_id: str = ""
    current_agent: str = ""
    history: list[str] = Field(default_factory=list)

    def add_result(self, agent_name: str, result: AgentResult):
        self.outputs[agent_name] = result
        self.total_cost += result.total_cost
        self.history.append(agent_name)

    def get_output(self, agent_name: str) -> str:
        r = self.outputs.get(agent_name)
        return r.content if r else ""

    def get_result(self, agent_name: str) -> AgentResult | None:
        return self.outputs.get(agent_name)

    def last_output(self) -> str:
        if not self.history: return self.task
        return self.get_output(self.history[-1])

    def build_prompt(self, agent_name: str) -> str:
        """Build a rich prompt with all previous agent outputs."""
        parts = [f"Original task: {self.task}"]
        for name in self.history:
            r = self.outputs.get(name)
            if r:
                tools = f" (tools: {', '.join(r.tool_calls_made)})" if r.tool_calls_made else ""
                parts.append(f"\n--- Output from {name}{tools} ---\n{r.content}")
        if self.shared:
            parts.append(f"\n--- Shared context ---\n{self.shared}")
        return "\n".join(parts)

    def set(self, key: str, value: Any): self.shared[key] = value
    def get(self, key: str, default: Any = None) -> Any: return self.shared.get(key, default)
