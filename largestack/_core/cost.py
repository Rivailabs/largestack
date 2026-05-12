"""Cost tracking, budget enforcement, and LLM pricing registry."""
from __future__ import annotations
from pathlib import Path
from largestack.errors import BudgetExceededError
from largestack.types import CostEstimate
import yaml

PRICING = {
    "gpt-5.2": {"in": 1.75, "out": 14.0, "cache": 0.88},
    "gpt-5-mini": {"in": 0.25, "out": 2.0, "cache": 0.13},
    "gpt-5-nano": {"in": 0.05, "out": 0.4},
    "gpt-4o": {"in": 2.5, "out": 10.0, "cache": 1.25},
    "gpt-4o-mini": {"in": 0.15, "out": 0.6, "cache": 0.075},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0, "cache": 0.5},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cache": 0.3},
    "claude-sonnet-4-20250514": {"in": 3.0, "out": 15.0, "cache": 0.3},
    "claude-haiku-4-5": {"in": 0.8, "out": 4.0, "cache": 0.08},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.0},
    "gemini-2.5-flash": {"in": 0.15, "out": 0.6},
    "deepseek-v3": {"in": 0.14, "out": 0.28},
    "deepseek-chat": {"in": 0.14, "out": 0.28},
}

class CostTracker:
    def __init__(self):
        self._p = dict(PRICING)
        pp = Path("pricing/models.yaml")
        if pp.exists():
            with open(pp) as f:
                d = yaml.safe_load(f) or {}
                for k, v in d.items():
                    self._p[k] = {"in": v.get("input", 0), "out": v.get("output", 0), "cache": v.get("cache_read", 0)}
        self._run = 0.0; self._total = 0.0; self._agents: dict[str, float] = {}
        self._run_tokens = 0; self._total_tokens = 0

    def calc(self, model: str, inp: int, out: int, cached: int = 0) -> float:
        mk = model.split("/")[-1].lower()
        pr = self._p.get(mk)
        if not pr:
            for k, v in self._p.items():
                if mk.startswith(k) or k.startswith(mk): pr = v; break
        if not pr: return 0.0
        return round(((inp - cached) / 1e6) * pr.get("in", 0) + (cached / 1e6) * pr.get("cache", pr.get("in", 0)) + (out / 1e6) * pr.get("out", 0), 6)

    def add(self, cost: float, agent: str = "default", tokens: int = 0):
        self._run += cost; self._total += cost
        self._agents[agent] = self._agents.get(agent, 0) + cost
        self._run_tokens += tokens; self._total_tokens += tokens

    def check(self, budget: float):
        if budget > 0 and self._run > budget: raise BudgetExceededError(self._run, budget)

    def reset(self): self._run = 0.0; self._run_tokens = 0

    def predict(self, model: str, inp: int) -> CostEstimate:
        est = int(inp * 1.5); exp = self.calc(model, inp, est)
        return CostEstimate(low=round(exp*0.5,6), expected=round(exp,6), high=round(exp*3,6), model=model, input_tokens=inp, estimated_output_tokens=est)

    @property
    def run_cost(self): return self._run
    @property
    def total_cost(self): return self._total
    @property
    def run_tokens(self): return self._run_tokens
    @property
    def total_tokens(self): return self._total_tokens
