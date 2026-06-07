"""v0.6.0: Tool retry strategy + circuit breaker tests."""

from __future__ import annotations

import asyncio
import time
from collections import deque

import pytest

from largestack._core.tools import ToolExecutor, ToolRegistry, tool
from largestack.types import ToolCall


# -------------------- Backoff strategies --------------------


def test_backoff_exponential_grows():
    delays = [ToolExecutor._backoff_delay(i, "exponential", 30.0, jitter=False) for i in range(4)]
    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_backoff_linear_grows():
    delays = [ToolExecutor._backoff_delay(i, "linear", 30.0, jitter=False) for i in range(4)]
    assert delays == [1.0, 2.0, 3.0, 4.0]


def test_backoff_constant_returns_one():
    for i in range(4):
        d = ToolExecutor._backoff_delay(i, "constant", 30.0, jitter=False)
        assert d == 1.0


def test_backoff_none_returns_zero():
    for i in range(4):
        assert ToolExecutor._backoff_delay(i, "none", 30.0, jitter=False) == 0.0


def test_backoff_max_caps_value():
    """Even at attempt 100 (2^100), delay must not exceed cap."""
    d = ToolExecutor._backoff_delay(100, "exponential", 5.0, jitter=False)
    assert d == 5.0


def test_backoff_jitter_in_band():
    """Jitter must keep result within ±25% of base."""
    base = 4.0
    samples = [ToolExecutor._backoff_delay(2, "exponential", 30.0, jitter=True) for _ in range(50)]
    for s in samples:
        assert 0.75 * base <= s <= 1.25 * base


# -------------------- Retry behavior --------------------


@pytest.mark.asyncio
async def test_retry_runs_n_plus_one_times():
    """retries=N means up to N+1 attempts total."""
    counter = {"n": 0}

    @tool(retries=3, backoff="none")
    async def flaky():
        counter["n"] += 1
        raise RuntimeError("boom")

    reg = ToolRegistry()
    reg.register(flaky)
    ex = ToolExecutor(reg)

    result = await ex.execute(ToolCall(id="t1", name="flaky", params={}))
    assert counter["n"] == 4  # 1 initial + 3 retries
    assert "boom" in (result.error or "")


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """Tool that fails once then succeeds returns the success result."""
    counter = {"n": 0}

    @tool(retries=2, backoff="none")
    async def flaky():
        counter["n"] += 1
        if counter["n"] < 2:
            raise RuntimeError("not yet")
        return "ok"

    reg = ToolRegistry()
    reg.register(flaky)
    ex = ToolExecutor(reg)

    result = await ex.execute(ToolCall(id="t1", name="flaky", params={}))
    assert counter["n"] == 2
    assert result.content == "ok"
    assert not result.error


# -------------------- Circuit breaker --------------------


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    """After N consecutive failures, the circuit opens and short-circuits."""
    counter = {"n": 0}

    @tool(
        retries=0,
        backoff="none",
        circuit_breaker_threshold=3,
        circuit_breaker_window_seconds=10.0,
        circuit_breaker_cooldown_seconds=10.0,
    )
    async def always_fail():
        counter["n"] += 1
        raise RuntimeError("down")

    reg = ToolRegistry()
    reg.register(always_fail)
    ex = ToolExecutor(reg)

    # 3 attempts trip the breaker
    for i in range(3):
        await ex.execute(ToolCall(id=f"t{i}", name="always_fail", params={}))

    assert counter["n"] == 3

    # 4th call must be short-circuited (no actual call to always_fail)
    result = await ex.execute(ToolCall(id="t4", name="always_fail", params={}))
    assert counter["n"] == 3, "tool was called despite open circuit"
    assert "Circuit open" in (result.error or "")


@pytest.mark.asyncio
async def test_circuit_breaker_disabled_by_default():
    """Without explicit threshold > 0, CB never opens."""
    counter = {"n": 0}

    @tool(retries=0, backoff="none")  # no CB config
    async def always_fail():
        counter["n"] += 1
        raise RuntimeError("down")

    reg = ToolRegistry()
    reg.register(always_fail)
    ex = ToolExecutor(reg)

    # 100 attempts — every one calls the tool
    for i in range(10):  # 10 is enough; default threshold = 0 = disabled
        await ex.execute(ToolCall(id=f"t{i}", name="always_fail", params={}))

    assert counter["n"] == 10


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets_failure_count():
    """A successful call wipes the prior failure count, preventing a
    later trip from a now-stale fault history."""
    state = {"calls": 0, "fail_until": 2}

    @tool(
        retries=0,
        backoff="none",
        circuit_breaker_threshold=3,
        circuit_breaker_window_seconds=10.0,
        circuit_breaker_cooldown_seconds=5.0,
    )
    async def sometimes_fail():
        state["calls"] += 1
        if state["calls"] <= state["fail_until"]:
            raise RuntimeError("flaky")
        return "ok"

    reg = ToolRegistry()
    reg.register(sometimes_fail)
    ex = ToolExecutor(reg)

    # 2 fails (under threshold), then 1 success — counter must reset
    await ex.execute(ToolCall(id="a", name="sometimes_fail", params={}))
    await ex.execute(ToolCall(id="b", name="sometimes_fail", params={}))
    res = await ex.execute(ToolCall(id="c", name="sometimes_fail", params={}))
    assert res.content == "ok"

    # Now make 2 more failures — without reset, this would trip CB.
    # With reset, CB stays closed.
    state["fail_until"] = 1000  # always fail again
    await ex.execute(ToolCall(id="d", name="sometimes_fail", params={}))
    await ex.execute(ToolCall(id="e", name="sometimes_fail", params={}))
    # 2 < threshold(3), so CB is still closed; next call still attempts the tool
    state["calls_before"] = state["calls"]
    await ex.execute(ToolCall(id="f", name="sometimes_fail", params={}))
    assert state["calls"] == state["calls_before"] + 1


@pytest.mark.asyncio
async def test_circuit_breaker_cooldown_then_recloses():
    """After cooldown elapses, circuit auto-closes and tool calls resume."""
    counter = {"n": 0}

    @tool(
        retries=0,
        backoff="none",
        circuit_breaker_threshold=2,
        circuit_breaker_window_seconds=10.0,
        circuit_breaker_cooldown_seconds=0.1,  # tiny cooldown
    )
    async def fail_then_recover():
        counter["n"] += 1
        if counter["n"] <= 2:
            raise RuntimeError("down")
        return "back"

    reg = ToolRegistry()
    reg.register(fail_then_recover)
    ex = ToolExecutor(reg)

    # Trip the breaker
    await ex.execute(ToolCall(id="1", name="fail_then_recover", params={}))
    await ex.execute(ToolCall(id="2", name="fail_then_recover", params={}))
    # Short-circuited
    res = await ex.execute(ToolCall(id="3", name="fail_then_recover", params={}))
    assert "Circuit open" in (res.error or "")
    assert counter["n"] == 2  # the short-circuit call did NOT invoke the tool

    # Wait out the cooldown
    await asyncio.sleep(0.15)

    # Now the call should go through (tool returns "back")
    res = await ex.execute(ToolCall(id="4", name="fail_then_recover", params={}))
    assert res.content == "back"


# -------------------- @tool decorator carries new attrs --------------------


def test_tool_decorator_attaches_v060_attributes():
    @tool(
        retries=5,
        backoff="linear",
        backoff_max_seconds=10.0,
        backoff_jitter=False,
        circuit_breaker_threshold=4,
        circuit_breaker_window_seconds=120.0,
        circuit_breaker_cooldown_seconds=60.0,
    )
    async def custom():
        return "x"

    assert custom._tool_retries == 5
    assert custom._tool_backoff == "linear"
    assert custom._tool_backoff_max == 10.0
    assert custom._tool_backoff_jitter is False
    assert custom._tool_cb_threshold == 4
    assert custom._tool_cb_window == 120.0
    assert custom._tool_cb_cooldown == 60.0


def test_tool_decorator_defaults_are_legacy_compatible():
    """No-config @tool must behave like v0.5 — same backoff (exponential),
    no circuit breaker."""

    @tool
    async def plain():
        return "x"

    # Defaults match v0.5 behavior
    assert plain._tool_backoff == "exponential"
    assert plain._tool_cb_threshold == 0  # disabled
