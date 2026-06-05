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
