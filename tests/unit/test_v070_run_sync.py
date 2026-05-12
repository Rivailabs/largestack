"""v0.7.0: ``Agent.run_sync()`` tests.

Verifies the synchronous wrapper works in scripts and refuses to run
from inside an already-active event loop (which would deadlock).
"""
from __future__ import annotations

import asyncio
import pytest


def test_run_sync_works_in_sync_context():
    """When called from synchronous code (no loop), run_sync executes."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="sync_test", llm="openai/gpt-4o-mini")
    with agent.override(model=TestModel(custom_output_text="hello sync")):
        result = agent.run_sync("test task")
    assert "hello sync" in result.content


def test_run_sync_supports_kwargs():
    """All run() kwargs forward correctly through run_sync()."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="sync_kw", llm="openai/gpt-4o-mini")
    with agent.override(model=TestModel(custom_output_text="ok")):
        # cost_budget + max_turns + timeout should pass through
        result = agent.run_sync("task", max_turns=3, cost_budget=0.05)
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_run_sync_raises_inside_event_loop():
    """Calling run_sync() from inside async code must raise — silent
    nested-loop attempts deadlock or fail unpredictably."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="loop_check", llm="openai/gpt-4o-mini")
    with agent.override(model=TestModel(custom_output_text="x")):
        with pytest.raises(RuntimeError, match="active event loop"):
            agent.run_sync("task")
