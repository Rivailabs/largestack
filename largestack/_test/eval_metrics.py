"""DeepEval 6 agent-specific metrics.

Layer 1 (Reasoning): PlanQuality, PlanAdherence
Layer 2 (Action): ToolCorrectness, ArgumentCorrectness
Layer 3 (Execution): TaskCompletion, StepEfficiency
"""

from __future__ import annotations
from typing import Any


class AgentMetrics:
    """Compute 6 agent evaluation metrics."""

    @staticmethod
    def task_completion(result: Any, expected: str = "", check_fn=None) -> float:
        """Did the agent achieve the goal? 0-1."""
        content = result.content if hasattr(result, "content") else str(result)
        if check_fn:
            return 1.0 if check_fn(content) else 0.0
        if expected:
            # Word overlap ratio
            exp_words = set(expected.lower().split())
            res_words = set(content.lower().split())
            return len(exp_words & res_words) / max(len(exp_words), 1)
        return 1.0 if content.strip() else 0.0

    @staticmethod
    def tool_correctness(actual_tools: list[str], expected_tools: list[str]) -> float:
        """Were the right tools called? 0-1."""
        if not expected_tools:
            return 1.0
        correct = sum(1 for t in expected_tools if t in actual_tools)
        return correct / len(expected_tools)

    @staticmethod
    def argument_correctness(actual_args: list[dict], expected_args: list[dict]) -> float:
        """Were tool parameters correct? 0-1."""
        if not expected_args:
            return 1.0
        correct = 0
        for exp in expected_args:
            for act in actual_args:
                if exp.items() <= act.items():
                    correct += 1
                    break
        return correct / len(expected_args)

    @staticmethod
    def step_efficiency(actual_steps: int, optimal_steps: int) -> float:
        """No wasted steps? 0-1 (1.0 = optimal, lower = wasteful)."""
        if optimal_steps <= 0:
            return 1.0
        if actual_steps <= optimal_steps:
            return 1.0
        return optimal_steps / actual_steps

    @staticmethod
    def plan_quality(plan_steps: list[str], task: str) -> float:
        """Was the plan appropriate for the task? Simple heuristic."""
        if not plan_steps:
            return 0.0
        task_words = set(task.lower().split())
        coverage = 0
        for step in plan_steps:
            step_words = set(step.lower().split())
            if task_words & step_words:
                coverage += 1
        return min(coverage / max(len(plan_steps), 1), 1.0)

    @staticmethod
    def plan_adherence(planned: list[str], executed: list[str]) -> float:
        """Did agent follow its plan? 0-1."""
        if not planned:
            return 1.0
        followed = sum(1 for p in planned if any(p.lower() in e.lower() for e in executed))
        return followed / len(planned)

    @classmethod
    def evaluate(
        cls, result, expected_tools=None, expected_args=None, optimal_steps=None, check_fn=None
    ) -> dict:
        """Run all applicable metrics."""
        metrics = {}
        metrics["task_completion"] = cls.task_completion(result, check_fn=check_fn)
        if expected_tools:
            tools = result.tool_calls_made if hasattr(result, "tool_calls_made") else []
            metrics["tool_correctness"] = cls.tool_correctness(tools, expected_tools)
        if optimal_steps:
            turns = result.turns if hasattr(result, "turns") else 1
            metrics["step_efficiency"] = cls.step_efficiency(turns, optimal_steps)
        return metrics
