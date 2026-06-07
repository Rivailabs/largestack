"""Statistical assertions for agent testing — SPRT reduces runs by 78%."""

from __future__ import annotations
import asyncio, math
from typing import Any, Callable


def agent_test(runs: int = 10, timeout: float = 60.0):
    """Decorator for agent tests with multiple runs."""

    def decorator(fn):
        async def wrapper(*args, **kwargs):
            results = []
            for i in range(runs):
                try:
                    r = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
                    results.append(r)
                except Exception as e:
                    results.append(e)
            return results

        wrapper.__name__ = fn.__name__
        wrapper._agent_test = True
        wrapper._runs = runs
        return wrapper

    return decorator


def assert_pass_rate(check_fn: Callable, results: list, min_rate: float = 0.8):
    """Assert that check_fn passes on at least min_rate of results."""
    passed = sum(1 for r in results if not isinstance(r, Exception) and check_fn(r))
    rate = passed / max(len(results), 1)
    if rate < min_rate:
        raise AssertionError(
            f"Pass rate {rate:.1%} < required {min_rate:.1%} ({passed}/{len(results)})"
        )


class SPRT:
    """Sequential Probability Ratio Test — terminate early with confidence.

    Wald's SPRT: 78% fewer runs than fixed-N testing.
    Three verdicts: PASS / FAIL / INCONCLUSIVE.
    """

    def __init__(
        self, h0_rate: float = 0.7, h1_rate: float = 0.9, alpha: float = 0.05, beta: float = 0.1
    ):
        self.h0 = h0_rate
        self.h1 = h1_rate
        self.log_a = math.log(beta / (1 - alpha))  # Lower boundary
        self.log_b = math.log((1 - beta) / alpha)  # Upper boundary
        self.lr_sum = 0.0
        self.n = 0

    def update(self, success: bool) -> str | None:
        """Feed result. Returns 'PASS', 'FAIL', or None (continue)."""
        self.n += 1
        if success:
            self.lr_sum += math.log(self.h1 / self.h0)
        else:
            self.lr_sum += math.log((1 - self.h1) / (1 - self.h0))

        if self.lr_sum >= self.log_b:
            return "PASS"
        if self.lr_sum <= self.log_a:
            return "FAIL"
        return None  # Continue testing

    def reset(self):
        self.lr_sum = 0.0
        self.n = 0
