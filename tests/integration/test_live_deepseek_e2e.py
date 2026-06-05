"""Live end-to-end checks against DeepSeek.

These run for real when LARGESTACK_DEEPSEEK_API_KEY is set (e.g. in CI via a
repository secret) and skip cleanly otherwise. They prove the wedge actually
works on the provider we promote — not just that the test suite is green.
"""
from __future__ import annotations

import os

import pytest
from pydantic import BaseModel, Field

from largestack import Agent, tool

SKIP = not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY")
pytestmark = pytest.mark.skipif(SKIP, reason="LARGESTACK_DEEPSEEK_API_KEY not set")

MODEL = "deepseek/deepseek-chat"


class Review(BaseModel):
    title: str
    rating: int = Field(ge=1, le=10)
    summary: str


async def test_typed_output_returns_validated_model_live():
    agent = Agent(name="typed", llm=MODEL, guardrails=None, max_turns=3)
    try:
        out = await agent.run(
            "Review the movie 'Inception': title, rating 1-10, and a one-line summary.",
            response_model=Review,
        )
        assert isinstance(out, Review)
        assert 1 <= out.rating <= 10
        assert out.title
    finally:
        await agent.aclose()


async def test_cost_is_tracked_live():
    agent = Agent(name="cost", llm=MODEL, guardrails=None)
    try:
        result = await agent.run("Say hello in exactly three words.")
        assert result.content
        assert result.total_cost > 0, "DeepSeek cost must be tracked, not $0"
    finally:
        await agent.aclose()


async def test_tool_calling_live():
    @tool
    async def add(a: int, b: int) -> str:
        """Add two integers."""
        return str(a + b)

    agent = Agent(name="tools", llm=MODEL, tools=[add], guardrails=None, max_turns=4)
    try:
        result = await agent.run("Use the add tool to compute 19 + 23, then state the result.")
        assert "42" in result.content
        assert "add" in result.tool_calls_made
        assert result.tool_calls_failed == []
    finally:
        await agent.aclose()
