"""Eval harness with bounded concurrency."""

from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field


@dataclass
class EvalCase:
    input: str
    expected: str
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalReport:
    total: int
    passed: int
    failed: int
    cases: list = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class EvalRunner:
    """Run agent against eval cases with concurrent execution."""

    def __init__(self, agent, match_fn=None, concurrency: int = 5):
        self.agent = agent
        self.match_fn = match_fn or (lambda actual, expected: expected.lower() in actual.lower())
        self.concurrency = concurrency

    async def run(self, cases: list[EvalCase]) -> EvalReport:
        t0 = time.time()
        sem = asyncio.Semaphore(self.concurrency)

        async def _run_case(case):
            async with sem:
                try:
                    r = await self.agent.run(case.input)
                    actual = (
                        r.content
                        if hasattr(r, "content")
                        else (r.output if hasattr(r, "output") else str(r))
                    )
                    ok = self.match_fn(actual, case.expected)
                    return {
                        "input": case.input,
                        "expected": case.expected,
                        "actual": actual[:200],
                        "passed": ok,
                        "error": None,
                    }
                except Exception as e:
                    return {
                        "input": case.input,
                        "expected": case.expected,
                        "actual": "",
                        "passed": False,
                        "error": str(e),
                    }

        results = await asyncio.gather(*[_run_case(c) for c in cases])
        passed = sum(1 for r in results if r["passed"])
        return EvalReport(
            total=len(cases),
            passed=passed,
            failed=len(cases) - passed,
            cases=results,
            duration_seconds=time.time() - t0,
        )
