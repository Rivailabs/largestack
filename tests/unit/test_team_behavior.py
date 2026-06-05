"""Behavioral tests for multi-agent Team — real execution, not source inspection.

Drives agents with deterministic test models and asserts on actual orchestration
behavior: context passing, parallel fan-out, and the skip/fail error policies.
"""
from __future__ import annotations

import pytest

from largestack import Agent, Team
from largestack.testing import FunctionModel, TestModel


def _text(t: str) -> TestModel:
    return TestModel(custom_output_text=t, call_tools=[])


async def test_sequential_passes_prior_output_to_next_agent():
    first = Agent(name="first", instructions="", guardrails=None)
    second = Agent(name="second", instructions="", guardrails=None)
    captured = FunctionModel(lambda msgs, info: {"content": "BETA"})
    team = Team(agents=[first, second], strategy="sequential")

    with first.override(model=_text("ALPHA-OUTPUT")), second.override(model=captured):
        result = await team.run("original task")

    # The second agent's prompt must contain the first agent's output.
    seen = " ".join(str(m.get("content", "")) for m in captured.messages_received)
    assert "ALPHA-OUTPUT" in seen
    assert result.content == "BETA"
    assert "first" in result.agent_name and "second" in result.agent_name


async def test_parallel_combines_both_outputs():
    a1 = Agent(name="p1", instructions="", guardrails=None)
    a2 = Agent(name="p2", instructions="", guardrails=None)
    team = Team(agents=[a1, a2], strategy="parallel")

    with a1.override(model=_text("ONE")), a2.override(model=_text("TWO")):
        result = await team.run("task")

    assert "ONE" in result.content and "TWO" in result.content
    assert result.agent_name == "team_parallel"


async def test_on_error_skip_continues_to_next_agent():
    bad = Agent(name="bad", instructions="", guardrails=None)
    good = Agent(name="good", instructions="", guardrails=None)

    def boom(msgs, info):
        raise RuntimeError("provider down")

    team = Team(agents=[bad, good], strategy="sequential", on_error="skip", retries_per_agent=1)
    with bad.override(model=FunctionModel(boom)), good.override(model=_text("RECOVERED")):
        result = await team.run("task")

    assert "RECOVERED" in result.content  # the good agent still ran


async def test_on_error_fail_raises():
    bad = Agent(name="bad", instructions="", guardrails=None)

    def boom(msgs, info):
        raise RuntimeError("kaboom")

    team = Team(agents=[bad], strategy="sequential", on_error="fail", retries_per_agent=1)
    with bad.override(model=FunctionModel(boom)):
        with pytest.raises(Exception):
            await team.run("task")


async def test_fallback_agent_used_when_primary_fails():
    primary = Agent(name="primary", instructions="", guardrails=None)
    backup = Agent(name="backup", instructions="", guardrails=None)

    def boom(msgs, info):
        raise RuntimeError("primary failed")

    team = Team(
        agents=[primary],
        strategy="sequential",
        on_error="skip",
        retries_per_agent=1,
        fallback_map={"primary": backup},
    )
    with primary.override(model=FunctionModel(boom)), backup.override(model=_text("FROM-BACKUP")):
        result = await team.run("task")

    assert "FROM-BACKUP" in result.content
