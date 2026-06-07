"""Agent registry — discover agents by name or capability."""

from __future__ import annotations
from typing import Any


class AgentRegistry:
    """Central registry for agent discovery in multi-agent systems.

    registry = AgentRegistry()
    registry.register(coder, capabilities=["python", "javascript"])
    registry.register(writer, capabilities=["blog", "report"])

    agent = registry.find(capability="python")  # Returns coder
    agents = registry.find_all(capability="report")
    """

    def __init__(self):
        self._agents: dict[str, dict] = {}

    def register(self, agent, capabilities: list[str] = None, tags: dict = None):
        self._agents[agent.name] = {
            "agent": agent,
            "capabilities": set(capabilities or []),
            "tags": tags or {},
            "llm": agent.llm,
            "tools": agent._reg.list_names() if hasattr(agent, "_reg") else [],
        }

    def get(self, name: str):
        entry = self._agents.get(name)
        return entry["agent"] if entry else None

    def find(self, capability: str = None, tag: str = None) -> Any | None:
        """Find first agent matching capability or tag."""
        for entry in self._agents.values():
            if capability and capability in entry["capabilities"]:
                return entry["agent"]
            if tag and tag in entry["tags"]:
                return entry["agent"]
        return None

    def find_all(self, capability: str = None) -> list:
        results = []
        for entry in self._agents.values():
            if capability and capability in entry["capabilities"]:
                results.append(entry["agent"])
        return results

    def list_agents(self) -> list[dict]:
        return [
            {
                "name": name,
                "capabilities": list(e["capabilities"]),
                "llm": e["llm"],
                "tools": e["tools"],
            }
            for name, e in self._agents.items()
        ]

    def unregister(self, name: str):
        self._agents.pop(name, None)

    def __len__(self):
        return len(self._agents)

    def __contains__(self, name: str):
        return name in self._agents
