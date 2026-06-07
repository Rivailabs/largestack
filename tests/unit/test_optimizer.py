"""Prompt optimizer tests."""

import sys, asyncio

sys.path.insert(0, ".")


def test_optimization_result_dataclass():
    from largestack._core.optimizer import OptimizationResult

    r = OptimizationResult(
        initial_prompt="x",
        best_prompt="y",
        initial_score=0.5,
        best_score=0.8,
        iterations=3,
        history=[],
    )
    assert r.best_score > r.initial_score


def test_optimizer_creates():
    from largestack._core.optimizer import PromptOptimizer

    opt = PromptOptimizer(metric=lambda p, e: 0.5)
    assert opt.max_iterations == 5
