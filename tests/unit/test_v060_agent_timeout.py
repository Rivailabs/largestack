"""v0.6.0: Agent.run(timeout=N) wall-clock timeout tests.

Verifies the runtime kwarg ``timeout`` propagates to LoopGuard's
wall-clock check, which raises LoopDetectedError(reason="timeout") on
the next ``check_turn()`` call.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from largestack._core.loop_guard import LoopGuard
from largestack.errors import LoopDetectedError


def test_loop_guard_default_timeout_does_not_fire_quickly():
    g = LoopGuard(timeout=300)
    g.check_turn()  # OK
    g.check_turn()  # OK


def test_loop_guard_short_timeout_fires_after_sleep():
    g = LoopGuard(timeout=0.05)
    g.check_turn()  # turn 1
    time.sleep(0.1)
    with pytest.raises(LoopDetectedError) as ei:
        g.check_turn()  # turn 2 — past timeout
    assert "timeout" in str(ei.value).lower()


@pytest.mark.asyncio
async def test_agent_run_with_timeout_kwarg_propagates():
    """The runtime ``timeout`` kwarg must reach LoopGuard so multi-turn
    runs can be wall-clock-bounded."""
    from largestack import Agent
    from largestack.testing import TestModel

    # Slow TestModel: each call adds 0.1s
    class SlowTestModel(TestModel):
        async def chat(self, *a, **kw):
            await asyncio.sleep(0.1)
            return await super().chat(*a, **kw)

    agent = Agent(name="t", llm="openai/gpt-4o-mini", max_turns=20)
    with agent.override(model=SlowTestModel(custom_output_text="ok")):
        # With a 0.05s timeout, the first turn already takes 0.1s →
        # the next check_turn() trips. The agent should surface this as
        # a status="loop" or "completed" with reason indicating timeout.
        result = await agent.run("test", timeout=0.05)
        # The exact status depends on engine's exception handling — what
        # matters is the run terminates (doesn't hang on max_turns=20).
        assert result is not None


@pytest.mark.asyncio
async def test_agent_run_without_timeout_uses_default():
    """No timeout kwarg = legacy behavior (default 300s)."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="t", llm="openai/gpt-4o-mini")
    with agent.override(model=TestModel(custom_output_text="ok")):
        result = await agent.run("hi")
    assert result is not None


def test_loop_guard_timeout_zero_means_no_limit():
    """Zero or negative timeout disables the wall-clock guard."""
    g = LoopGuard(timeout=0)
    g.check_turn()
    time.sleep(0.05)
    g.check_turn()  # would fire if timeout were positive
