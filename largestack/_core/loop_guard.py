"""5-layer loop termination: max_iter + cost + fingerprint + no-progress + timeout."""

from __future__ import annotations
import hashlib, json, time
from largestack.errors import BudgetExceededError, LoopDetectedError
from largestack.types import ToolCall


class LoopGuard:
    def __init__(self, max_turns=25, cost_budget=5.0, max_repeats=3, no_progress=5, timeout=300.0):
        self.max_turns = max_turns
        self.cost_budget = cost_budget
        self.max_repeats = max_repeats
        self.no_progress = no_progress
        self.timeout = timeout
        self._t0 = time.monotonic()
        self._hashes: list[str] = []
        self._outs: list[str] = []
        self._turn = 0
        self._cost = 0.0

    def check_turn(self):
        self._turn += 1
        if self._turn > self.max_turns:
            raise LoopDetectedError(self._turn, "max_turns")
        # v0.6.0: timeout<=0 disables the wall-clock guard (consistent with
        # cost_budget=0 meaning "no cap").
        if self.timeout > 0 and time.monotonic() - self._t0 > self.timeout:
            raise LoopDetectedError(self._turn, "timeout")

    def check_cost(self, cost: float):
        self._cost += cost
        if self.cost_budget > 0 and self._cost > self.cost_budget:
            raise BudgetExceededError(self._cost, self.cost_budget)

    def check_cost_pre_call(self, projected_cost: float = 0.0):
        """v0.6.0: hard pre-flight check before issuing an LLM call.

        ``projected_cost`` is an optional best-guess of the upcoming call's
        cost. If we're already over budget, raise immediately without making
        the API call. Even with projected_cost=0, this still catches the case
        where prior turns already pushed us over.
        """
        if self.cost_budget <= 0:
            return
        if self._cost + projected_cost > self.cost_budget:
            raise BudgetExceededError(
                self._cost + projected_cost,
                self.cost_budget,
            )

    @property
    def remaining_budget(self) -> float:
        """v0.6.0: how much budget is left. Returns inf when no cap is set."""
        if self.cost_budget <= 0:
            return float("inf")
        return max(0.0, self.cost_budget - self._cost)

    def check_loop(self, tcs: list[ToolCall]) -> bool:
        if not tcs:
            return False
        h = hashlib.sha256(
            json.dumps([(t.name, json.dumps(t.params, sort_keys=True)) for t in tcs]).encode()
        ).hexdigest()
        self._hashes.append(h)
        if (
            len(self._hashes) >= self.max_repeats
            and len(set(self._hashes[-self.max_repeats :])) == 1
        ):
            return True
        return False

    def check_progress(self, out: str) -> bool:
        self._outs.append(hashlib.sha256(out.encode()).hexdigest())
        if len(self._outs) >= self.no_progress and len(set(self._outs[-self.no_progress :])) <= 2:
            return True
        return False

    @property
    def turn(self):
        return self._turn

    @property
    def elapsed(self):
        return time.monotonic() - self._t0
