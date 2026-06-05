"""`tool_calls_made` over-reported: it counts attempted calls, including ones whose
execution errored. These cover the new `tool_calls_failed` field, which records the
subset that errored so observability reflects what actually succeeded.
"""
from __future__ import annotations

from largestack import Agent, tool
from largestack.testing import TestModel


@tool
async def boom(x: str = "y") -> str:
    """A tool that always raises."""
    raise RuntimeError("kaboom")


@tool
async def ok_tool(x: str = "y") -> str:
    """A tool that succeeds."""
    return "fine"


async def test_failed_tool_recorded_in_tool_calls_failed():
    agent = Agent(name="t", instructions="", tools=[boom], guardrails=None)
    with agent.override(model=TestModel(custom_output_text="done", call_tools=["boom"])):
        r = await agent.run("go")
    # Existing contract preserved: the attempt is still in tool_calls_made.
    assert "boom" in r.tool_calls_made
    # New accuracy: the failed execution is recorded.
    assert "boom" in r.tool_calls_failed


async def test_succeeding_tool_not_in_failed():
    agent = Agent(name="t2", instructions="", tools=[ok_tool], guardrails=None)
    with agent.override(model=TestModel(custom_output_text="done", call_tools=["ok_tool"])):
        r = await agent.run("go")
    assert "ok_tool" in r.tool_calls_made
    assert r.tool_calls_failed == []


def test_agentresult_has_failed_field_default():
    from largestack.types import AgentResult

    r = AgentResult(content="x", agent_name="a")
    assert r.tool_calls_failed == []
