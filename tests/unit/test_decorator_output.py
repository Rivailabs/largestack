"""The typed decorator API must honor output_type: a Pydantic output_type must
return a validated model instance, not a raw string. Regression guard for the gap
where Agent[Deps, Model](output_type=Model) returned result.content (a str).
"""

from __future__ import annotations

from pydantic import BaseModel

from largestack.decorators import Agent
from largestack.testing import FunctionModel


class Out(BaseModel):
    name: str
    n: int


async def test_decorator_output_type_returns_typed_model():
    agent = Agent("deepseek/deepseek-chat", output_type=Out, instructions="return json")
    with agent.override(model=FunctionModel(lambda m, i: {"content": '{"name": "alice", "n": 7}'})):
        r = await agent.run("classify")
    assert isinstance(r.output, Out)
    assert r.output.name == "alice" and r.output.n == 7


async def test_decorator_output_type_parses_fenced_json():
    agent = Agent("deepseek/deepseek-chat", output_type=Out, instructions="return json")
    fenced = '```json\n{"name": "bob", "n": 3}\n```'
    with agent.override(model=FunctionModel(lambda m, i: {"content": fenced})):
        r = await agent.run("classify")
    assert isinstance(r.output, Out) and r.output.n == 3


async def test_decorator_str_output_unchanged():
    agent = Agent("deepseek/deepseek-chat", instructions="echo")
    with agent.override(model=FunctionModel(lambda m, i: {"content": "plain text"})):
        r = await agent.run("hi")
    assert r.output == "plain text"


def test_decorator_late_tool_registration_invalidates_cache():
    """A tool registered AFTER the underlying agent is materialized must be picked up
    (regression: _underlying_agent was cached and ignored later tool registrations)."""
    agent = Agent("deepseek/deepseek-chat", instructions="x")

    @agent.tool_plain
    def first(x: int) -> int:
        "first tool"
        return x

    u1 = agent._get_underlying()  # materialize the underlying agent
    assert u1 is not None
    assert agent._underlying_agent is u1  # cached

    @agent.tool_plain
    def second(y: int) -> int:
        "second tool registered AFTER materialization"
        return y

    assert agent._underlying_agent is None  # registration invalidated the cache
    u2 = agent._get_underlying()
    assert u2 is not u1  # rebuilt
    # the late tool is now actually in the underlying agent's registry
    assert u2._tool_registry.get("second") is not None
    assert u2._tool_registry.get("first") is not None
