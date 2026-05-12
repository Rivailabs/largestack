"""Agent health monitoring — track agent status, uptime, error rates.

    monitor = AgentMonitor()
    monitor.register(agent)
    health = monitor.check_all()
    # {"researcher": {"status": "healthy", "uptime_s": 3600, "error_rate": 0.02}}
"""
from __future__ import annotations
import time, logging
from typing import Any

log = logging.getLogger("largestack.health")

class AgentHealth:
    def __init__(self, name: str):
        self.name = name
        self.total_runs = 0; self.failed_runs = 0
        self.total_cost = 0.0; self.total_latency_ms = 0.0
        self.last_run_at = 0.0; self.registered_at = time.time()
        self.last_error: str = ""

    def record_success(self, cost: float, latency_ms: float, quality_score: float = None):
        """Record success. Optional quality_score (0-1) for silent failure detection."""
        self._quality_scores = getattr(self, '_quality_scores', [])
        self.total_runs += 1; self.total_cost += cost
        self.total_latency_ms += latency_ms; self.last_run_at = time.time()
        if quality_score is not None:
            self._quality_scores.append(quality_score)
            if len(self._quality_scores) > 100: self._quality_scores = self._quality_scores[-100:]

    def record_failure(self, error: str):
        self.total_runs += 1; self.failed_runs += 1
        self.last_error = error; self.last_run_at = time.time()

    @property
    def error_rate(self) -> float:
        return self.failed_runs / max(self.total_runs, 1)

    @property
    def avg_latency_ms(self) -> float:
        successful = self.total_runs - self.failed_runs
        return self.total_latency_ms / max(successful, 1)

    @property
    def avg_quality(self) -> float:
        scores = getattr(self, '_quality_scores', [])
        return sum(scores) / max(len(scores), 1) if scores else 1.0

    @property
    def silent_failure_rate(self) -> float:
        """Rate of responses that succeeded but had low quality (<0.3)."""
        scores = getattr(self, '_quality_scores', [])
        if not scores: return 0.0
        return sum(1 for s in scores if s < 0.3) / len(scores)

    @property
    def status(self) -> str:
        if self.total_runs == 0: return "idle"
        if self.error_rate > 0.5: return "unhealthy"
        if self.error_rate > 0.1: return "degraded"
        if self.silent_failure_rate > 0.3: return "degraded"  # Responds but doesn't solve
        return "healthy"

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "total_runs": self.total_runs,
                "failed_runs": self.failed_runs, "error_rate": round(self.error_rate, 3),
                "total_cost": round(self.total_cost, 4),
                "avg_latency_ms": round(self.avg_latency_ms, 1),
                "uptime_s": round(time.time() - self.registered_at, 1),
                "last_error": self.last_error, "avg_quality": round(self.avg_quality, 3),
                "silent_failure_rate": round(self.silent_failure_rate, 3)}

class AgentMonitor:
    """Monitor health of multiple agents."""
    def __init__(self):
        self._agents: dict[str, AgentHealth] = {}

    def register(self, agent):
        self._agents[agent.name] = AgentHealth(agent.name)

    def record(self, agent_name: str, success: bool, cost: float = 0, latency_ms: float = 0, error: str = "", quality_score: float = None):
        h = self._agents.get(agent_name)
        if not h: h = AgentHealth(agent_name); self._agents[agent_name] = h
        if success: h.record_success(cost, latency_ms, quality_score=quality_score)
        else: h.record_failure(error)

    def check(self, agent_name: str) -> dict:
        h = self._agents.get(agent_name)
        return h.to_dict() if h else {"status": "unknown"}

    def check_all(self) -> dict[str, dict]:
        return {name: h.to_dict() for name, h in self._agents.items()}

    def unhealthy_agents(self) -> list[str]:
        return [n for n, h in self._agents.items() if h.status in ("unhealthy", "degraded")]
