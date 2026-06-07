"""Regression testing — catch agent quality degradation automatically.

suite = RegressionSuite("tests/fixtures/golden.json")
suite.add("What is 2+2?", expected_contains="4")
suite.add("Translate hello to French", expected_contains="bonjour")
results = await suite.run(agent)
# {"passed": 9, "failed": 1, "regression": True, "details": [...]}
"""

from __future__ import annotations
import json, os, time
from typing import Any


class RegressionCase:
    def __init__(
        self,
        task: str,
        expected_contains: str = None,
        expected_not_contains: str = None,
        max_cost: float = None,
        max_turns: int = None,
        required_tools: list[str] = None,
    ):
        self.task = task
        self.expected_contains = expected_contains
        self.expected_not_contains = expected_not_contains
        self.max_cost = max_cost
        self.max_turns = max_turns
        self.required_tools = required_tools or []


class RegressionSuite:
    """Run golden test cases against an agent and detect regressions."""

    def __init__(self, fixture_path: str = None):
        self.cases: list[RegressionCase] = []
        self._fixture_path = fixture_path
        if fixture_path and os.path.exists(fixture_path):
            self._load(fixture_path)

    def add(self, task: str, **kw):
        self.cases.append(RegressionCase(task, **kw))

    async def run(self, agent, save_results: bool = True) -> dict:
        results = {"passed": 0, "failed": 0, "cases": [], "timestamp": time.time()}
        for case in self.cases:
            try:
                result = await agent.run(case.task)
                passed = True
                reasons = []

                if (
                    case.expected_contains
                    and case.expected_contains.lower() not in result.content.lower()
                ):
                    passed = False
                    reasons.append(f"Missing: '{case.expected_contains}'")
                if (
                    case.expected_not_contains
                    and case.expected_not_contains.lower() in result.content.lower()
                ):
                    passed = False
                    reasons.append(f"Contains forbidden: '{case.expected_not_contains}'")
                if case.max_cost and result.total_cost > case.max_cost:
                    passed = False
                    reasons.append(f"Cost ${result.total_cost:.4f} > ${case.max_cost:.4f}")
                if case.max_turns and result.turns > case.max_turns:
                    passed = False
                    reasons.append(f"Turns {result.turns} > {case.max_turns}")
                if case.required_tools:
                    missing = set(case.required_tools) - set(result.tool_calls_made)
                    if missing:
                        passed = False
                        reasons.append(f"Missing tools: {missing}")

                results["passed" if passed else "failed"] += 1
                results["cases"].append(
                    {
                        "task": case.task,
                        "passed": passed,
                        "reasons": reasons,
                        "content": result.content[:200],
                        "cost": result.total_cost,
                    }
                )
            except Exception as e:
                results["failed"] += 1
                results["cases"].append({"task": case.task, "passed": False, "reasons": [str(e)]})

        results["regression"] = results["failed"] > 0
        results["pass_rate"] = results["passed"] / max(len(self.cases), 1)

        if save_results and self._fixture_path:
            with open(self._fixture_path.replace(".json", "_results.json"), "w") as f:
                json.dump(results, f, indent=2)
        return results

    def save(self, path: str = None):
        path = path or self._fixture_path
        data = [
            {
                "task": c.task,
                "expected_contains": c.expected_contains,
                "expected_not_contains": c.expected_not_contains,
                "max_cost": c.max_cost,
                "max_turns": c.max_turns,
                "required_tools": c.required_tools,
            }
            for c in self.cases
        ]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self, path: str):
        with open(path) as f:
            for item in json.load(f):
                self.cases.append(RegressionCase(**item))
