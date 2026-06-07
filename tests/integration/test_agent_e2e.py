"""Integration tests — require LARGESTACK_DEEPSEEK_API_KEY or skip."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import inspect
import os

import pytest


SKIP = not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY")
reason = "Set LARGESTACK_DEEPSEEK_API_KEY to run integration tests"


async def _settle_live_transports() -> None:
    """Allow httpx/httpcore/anyio network transports to finalize."""
    with contextlib.suppress(Exception):
        await asyncio.sleep(0)
        await asyncio.sleep(0.25)
        gc.collect()
        await asyncio.sleep(0)


async def _close_obj(obj) -> None:
    """Best-effort cleanup for Agent/Team/provider objects."""
    if obj is None:
        return

    seen: set[int] = set()

    async def _close(current) -> None:
        if current is None:
            return

        oid = id(current)
        if oid in seen:
            return
        seen.add(oid)

        # Close child providers first.
        providers = getattr(current, "providers", None)
        if isinstance(providers, dict):
            for provider in list(providers.values()):
                await _close(provider)

        # Close nested children.
        for name in (
            "agents",
            "_agents",
            "_gw",
            "gateway",
            "_engine",
            "engine",
            "_provider",
            "provider",
            "_llm_provider",
            "llm_provider",
            "_client",
            "client",
            "_c",
            "_llm",
            "llm",
            "_router",
            "router",
        ):
            child = getattr(current, name, None)
            if child is None or child is current:
                continue

            if isinstance(child, dict):
                for value in child.values():
                    await _close(value)
            elif isinstance(child, (list, tuple, set)):
                for value in child:
                    await _close(value)
            else:
                await _close(child)

        # Close current object itself.
        close = getattr(current, "aclose", None) or getattr(current, "close", None)
        if close is not None:
            with contextlib.suppress(Exception):
                result = close()
                if inspect.isawaitable(result):
                    await result

    await _close(obj)
    await _settle_live_transports()


async def _run_and_close_agent(agent, prompt):
    try:
        return await agent.run(prompt)
    finally:
        await _close_obj(agent)


async def _run_and_close_team(team, prompt):
    try:
        return await team.run(prompt)
    finally:
        await _close_obj(team)


@pytest.mark.skipif(SKIP, reason=reason)
def test_basic_chat():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent

    agent = Agent(
        name="int-test",
        instructions="Under 20 words.",
        llm="deepseek/deepseek-chat",
        guardrails=None,
    )
    r = asyncio.run(_run_and_close_agent(agent, "What is 2+2?"))

    assert r.content and r.turns >= 1 and r.total_cost >= 0
    assert r.trace_id and len(r.trace_id) > 0


@pytest.mark.skipif(SKIP, reason=reason)
def test_tool_calling():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent, tool

    @tool
    async def multiply(a: int, b: int) -> str:
        """Multiply two numbers."""
        return str(a * b)

    agent = Agent(
        name="tool-int",
        instructions="Use multiply tool.",
        tools=[multiply],
        llm="deepseek/deepseek-chat",
        guardrails=None,
    )
    r = asyncio.run(_run_and_close_agent(agent, "What is 7 * 8?"))

    assert "56" in r.content or "multiply" in r.tool_calls_made


@pytest.mark.skipif(SKIP, reason=reason)
def test_team_sequential():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent, Team

    team = Team(
        agents=[
            Agent(
                name="r",
                instructions="List 2 facts.",
                llm="deepseek/deepseek-chat",
                guardrails=None,
            ),
            Agent(
                name="w",
                instructions="Summarize in 1 sentence.",
                llm="deepseek/deepseek-chat",
                guardrails=None,
            ),
        ]
    )
    r = asyncio.run(_run_and_close_team(team, "Python programming"))

    assert r.content and r.total_cost > 0


@pytest.mark.skipif(SKIP, reason=reason)
def test_guardrails_active():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent

    agent = Agent(
        name="guard-int",
        instructions="Answer briefly.",
        llm="deepseek/deepseek-chat",
    )
    r = asyncio.run(_run_and_close_agent(agent, "What is machine learning?"))

    assert r.content


@pytest.mark.skipif(SKIP, reason=reason)
def test_cost_tracked():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent

    agent = Agent(
        name="cost-int",
        instructions="Say hello.",
        llm="deepseek/deepseek-chat",
        guardrails=None,
    )
    r = asyncio.run(_run_and_close_agent(agent, "Hello"))

    assert r.total_cost >= 0


@pytest.mark.skipif(SKIP, reason=reason)
def test_metrics_populated():
    import sys

    sys.path.insert(0, ".")
    from largestack import Agent

    agent = Agent(
        name="met-int",
        instructions="Say ok.",
        llm="deepseek/deepseek-chat",
        guardrails=None,
    )
    asyncio.run(_run_and_close_agent(agent, "Say ok"))

    from largestack._observe.metrics import metrics

    output = metrics.format_prometheus()
    assert "largestack_llm_requests_total" in output
