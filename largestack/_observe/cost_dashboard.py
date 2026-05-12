"""Real-time cost monitoring dashboard."""
from __future__ import annotations
import json, time
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CostMonitor:
    """Tracks costs by agent, model, time window."""
    by_agent: dict = field(default_factory=lambda: defaultdict(float))
    by_model: dict = field(default_factory=lambda: defaultdict(float))
    by_hour: dict = field(default_factory=lambda: defaultdict(float))
    total: float = 0.0
    
    def record(self, cost: float, agent: str = "default", model: str = "unknown"):
        self.by_agent[agent] += cost
        self.by_model[model] += cost
        hour = time.strftime("%Y-%m-%d %H:00")
        self.by_hour[hour] += cost
        self.total += cost
    
    def report(self) -> dict:
        return {
            "total": round(self.total, 6),
            "top_agents": dict(sorted(self.by_agent.items(),
                                       key=lambda x: -x[1])[:5]),
            "top_models": dict(sorted(self.by_model.items(),
                                       key=lambda x: -x[1])[:5]),
            "by_hour": dict(self.by_hour),
        }
    
    def alert_if_over(self, threshold: float) -> bool:
        return self.total > threshold
