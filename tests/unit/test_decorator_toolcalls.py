"""The typed decorator AgentRunResult must expose tool_calls_made / tool_calls_failed
(parity with the legacy Agent), so callers have tool observability.
"""

from __future__ import annotations

from largestack.decorators import Agent
from largestack.testing import TestModel


def test_agentrunresult_has_tool_call_fields():
    from largestack.decorators import AgentRunResult

    r = AgentRunResult(output="x", usage={})
    assert r.tool_calls_made == [] and r.tool_calls_failed == []


async def test_decorator_passes_through_tool_calls():
    agent = Agent("deepseek/deepseek-chat", instructions="use tools")

    @agent.tool_plain
    def ping(x: str = "y") -> str:
        """ping tool"""
        return "pong"

    with agent.override(model=TestModel(custom_output_text="done", call_tools=["ping"])):
        r = await agent.run("go")
    assert "ping" in r.tool_calls_made
