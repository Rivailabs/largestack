"""Smart routing — Thompson Sampling bandit for model selection.

Learns best model per task type via exploration/exploitation.
Tiers: nano($0.05) → mini($0.25) → sonnet($3) → opus($5)
"""
from __future__ import annotations
import random, math, logging
from typing import Any
from collections import defaultdict

log = logging.getLogger("largestack.router")

class SmartRouter:
    """Thompson Sampling model router — auto-learns best model per task type."""
    
    MODEL_TIERS = {
        "simple": ["gpt-4o-mini", "gemini-2.5-flash", "deepseek-chat"],
        "moderate": ["gpt-4o", "claude-haiku-4-5", "gemini-2.5-pro"],
        "complex": ["claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o"],
        "premium": ["claude-opus-4-6", "o3"],
    }
    
    def __init__(self):
        # Beta distribution params per model: (successes, failures)
        self._betas: dict[str, tuple[float, float]] = defaultdict(lambda: (1.0, 1.0))
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._costs: dict[str, list[float]] = defaultdict(list)
    
    def select(self, tier: str = "moderate", strategy: str = "balanced") -> str:
        """Select best model using Thompson Sampling."""
        candidates = self.MODEL_TIERS.get(tier, self.MODEL_TIERS["moderate"])
        
        if strategy == "cost":
            return candidates[0]  # Cheapest first
        elif strategy == "quality":
            return candidates[-1]  # Most expensive = highest quality
        
        # Thompson Sampling: sample from Beta distributions
        best_model = candidates[0]
        best_sample = -1.0
        for model in candidates:
            alpha, beta_param = self._betas[model]
            sample = random.betavariate(max(alpha, 0.1), max(beta_param, 0.1))
            if sample > best_sample:
                best_sample = sample
                best_model = model
        return best_model
    
    def update(self, model: str, success: bool, latency_ms: float = 0, cost: float = 0):
        """Update model stats after a call."""
        alpha, beta_param = self._betas[model]
        if success:
            self._betas[model] = (alpha + 1, beta_param)
        else:
            self._betas[model] = (alpha, beta_param + 1)
        if latency_ms > 0:
            self._latencies[model].append(latency_ms)
        if cost > 0:
            self._costs[model].append(cost)
    
    def estimate_complexity(self, messages: list[dict], has_tools: bool = False) -> str:
        """Estimate task complexity from messages."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars < 200 and not has_tools: return "simple"
        elif total_chars < 1000: return "moderate"
        elif total_chars < 4000: return "complex"
        return "premium"
    
    def get_stats(self) -> dict[str, dict]:
        """Get stats for all models."""
        stats = {}
        for model, (a, b) in self._betas.items():
            lats = self._latencies.get(model, [])
            costs = self._costs.get(model, [])
            stats[model] = {
                "success_rate": a / (a + b),
                "total_calls": int(a + b - 2),
                "avg_latency_ms": sum(lats) / len(lats) if lats else 0,
                "avg_cost": sum(costs) / len(costs) if costs else 0,
            }
        return stats
