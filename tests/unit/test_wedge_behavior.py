"""Behavioral tests for core wedge pieces: loop-guard budget enforcement, agent
run/clone. Real behavior, not source-string checks.
"""

from __future__ import annotations

import pytest

from largestack import Agent
from largestack._core.loop_guard import LoopGuard
from largestack.errors import BudgetExceededError, LoopDetectedError
from largestack.testing import TestModel


# ---- LoopGuard ------------------------------------------------------------


def test_cost_budget_enforced_when_exceeded():
    g = LoopGuard(cost_budget=0.01)
    g.check_cost(0.005)  # under budget — fine
    with pytest.raises(BudgetExceededError):
        g.check_cost(0.02)  # cumulative 0.025 > 0.01


def test_cost_budget_zero_means_unlimited():
    g = LoopGuard(cost_budget=0)
    g.check_cost(1000.0)  # must not raise when budget disabled


def test_max_turns_enforced():
    g = LoopGuard(max_turns=2, timeout=0)
    g.check_turn()
    g.check_turn()
    with pytest.raises(LoopDetectedError):
        g.check_turn()  # 3rd turn over the limit


# ---- Agent ----------------------------------------------------------------


async def test_agent_run_returns_model_output():
    a = Agent(name="echo", instructions="", guardrails=None)
    with a.override(model=TestModel(custom_output_text="hello world", call_tools=[])):
        r = await a.run("hi")
    assert r.content == "hello world"
    assert r.agent_name == "echo"
    assert r.tool_calls_failed == []


def test_agent_clone_overrides_name_not_original():
    a = Agent(name="orig", instructions="base", guardrails=None)
    b = a.clone(name="cloned")
    assert b.name == "cloned"
    assert a.name == "orig"
