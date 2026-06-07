"""v0.10.0: Tests for retry + circuit breaker utilities."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest


# -------------------- retry decorator --------------------


@pytest.mark.asyncio
async def test_retry_succeeds_first_try():
    from largestack._core.resilience import retry

    calls = 0

    @retry(max_attempts=3, initial_delay=0.01, jitter=False)
    async def fn():
        nonlocal calls
        calls += 1
        return "ok"

    result = await fn()
    assert result == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_failures():
    from largestack._core.resilience import retry

    calls = 0

    @retry(max_attempts=4, initial_delay=0.01, jitter=False)
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_raises():
    from largestack._core.resilience import retry, RetryError

    calls = 0

    @retry(max_attempts=3, initial_delay=0.01, jitter=False)
    async def always_fails():
        nonlocal calls
        calls += 1
        raise ValueError("boom")

    with pytest.raises(RetryError) as exc_info:
        await always_fails()
    assert calls == 3
    assert isinstance(exc_info.value.last_exception, ValueError)


@pytest.mark.asyncio
async def test_retry_only_specific_exceptions():
    from largestack._core.resilience import retry

    @retry(
        max_attempts=3,
        initial_delay=0.01,
        jitter=False,
        retry_on=(ValueError,),
    )
    async def fn():
        raise TypeError("won't be caught")

    with pytest.raises(TypeError):
        await fn()


@pytest.mark.asyncio
async def test_retry_do_not_retry_takes_precedence():
    from largestack._core.resilience import retry

    calls = 0

    @retry(
        max_attempts=5,
        initial_delay=0.01,
        jitter=False,
        retry_on=(Exception,),
        do_not_retry_on=(ValueError,),
    )
    async def fn():
        nonlocal calls
        calls += 1
        raise ValueError("never retry me")

    with pytest.raises(ValueError):
        await fn()
    assert calls == 1  # never retried


@pytest.mark.asyncio
async def test_retry_with_config():
    from largestack._core.resilience import retry_with, RetryConfig

    cfg = RetryConfig(max_attempts=2, initial_delay=0.01, jitter=False)
    calls = 0

    @retry_with(cfg)
    async def fn():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError()
        return "done"

    result = await fn()
    assert result == "done"


def test_retry_config_delay_grows_exponentially():
    from largestack._core.resilience import RetryConfig

    cfg = RetryConfig(
        initial_delay=1.0,
        max_delay=100.0,
        backoff_multiplier=2.0,
        jitter=False,
    )
    assert cfg.delay_for_attempt(1) == 1.0
    assert cfg.delay_for_attempt(2) == 2.0
    assert cfg.delay_for_attempt(3) == 4.0
    assert cfg.delay_for_attempt(10) == 100.0  # capped


# -------------------- CircuitBreaker --------------------


@pytest.mark.asyncio
async def test_breaker_starts_closed():
    from largestack._core.resilience import CircuitBreaker

    cb = CircuitBreaker(name="test")
    assert cb.is_closed
    assert not cb.is_open


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold_failures():
    from largestack._core.resilience import CircuitBreaker, CircuitOpenError

    cb = CircuitBreaker(name="t", failure_threshold=3, recovery_timeout=10)

    for i in range(3):
        try:
            async with cb:
                raise RuntimeError(f"fail {i}")
        except RuntimeError:
            pass

    assert cb.is_open

    # Subsequent calls fail fast without invoking the protected code
    invoked = False
    try:
        async with cb:
            invoked = True
    except CircuitOpenError:
        pass
    assert not invoked


@pytest.mark.asyncio
async def test_breaker_resets_failures_on_success():
    from largestack._core.resilience import CircuitBreaker

    cb = CircuitBreaker(name="t", failure_threshold=3)

    # Two failures
    for _ in range(2):
        try:
            async with cb:
                raise RuntimeError()
        except RuntimeError:
            pass

    # Success resets counter
    async with cb:
        pass

    assert cb.is_closed
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_breaker_half_open_after_recovery_timeout():
    from largestack._core.resilience import CircuitBreaker, CircuitOpenError

    cb = CircuitBreaker(
        name="t",
        failure_threshold=2,
        recovery_timeout=0.05,
    )
    # Trip the breaker
    for _ in range(2):
        try:
            async with cb:
                raise RuntimeError()
        except RuntimeError:
            pass
    assert cb.is_open

    # Wait past recovery timeout
    await asyncio.sleep(0.06)

    # First call → HALF_OPEN, success → CLOSED
    async with cb:
        pass
    assert cb.is_closed


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens():
    from largestack._core.resilience import CircuitBreaker

    cb = CircuitBreaker(
        name="t",
        failure_threshold=2,
        recovery_timeout=0.05,
    )
    for _ in range(2):
        try:
            async with cb:
                raise RuntimeError()
        except RuntimeError:
            pass

    await asyncio.sleep(0.06)

    # Trial call fails → back to OPEN
    try:
        async with cb:
            raise RuntimeError("trial failed")
    except RuntimeError:
        pass

    assert cb.is_open


@pytest.mark.asyncio
async def test_breaker_decorator():
    from largestack._core.resilience import CircuitBreaker, CircuitOpenError

    cb = CircuitBreaker(name="t", failure_threshold=2)

    @cb.protect
    async def call(should_fail=False):
        if should_fail:
            raise RuntimeError()
        return "ok"

    # Two failures opens it
    for _ in range(2):
        try:
            await call(should_fail=True)
        except RuntimeError:
            pass

    # Now fails fast
    with pytest.raises(CircuitOpenError):
        await call()


@pytest.mark.asyncio
async def test_breaker_reset():
    from largestack._core.resilience import CircuitBreaker

    cb = CircuitBreaker(name="t", failure_threshold=1)
    try:
        async with cb:
            raise RuntimeError()
    except RuntimeError:
        pass
    assert cb.is_open

    cb.reset()
    assert cb.is_closed
    assert cb.failures == 0


# -------------------- resilient (combined) --------------------


@pytest.mark.asyncio
async def test_resilient_retries_and_succeeds():
    from largestack._core.resilience import resilient

    calls = 0

    @resilient(max_attempts=3, retry_on=(RuntimeError,))
    async def fn():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError()
        return "ok"

    result = await fn()
    assert result == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_resilient_with_breaker_trips_after_persistent_failure():
    from largestack._core.resilience import (
        resilient,
        CircuitBreaker,
        RetryError,
        CircuitOpenError,
    )

    cb = CircuitBreaker(name="t", failure_threshold=2)
    calls = 0

    @resilient(max_attempts=3, breaker=cb, retry_on=(RuntimeError,))
    async def fn():
        nonlocal calls
        calls += 1
        raise RuntimeError("always fails")

    # Either the retries get exhausted (RetryError) or the breaker opens
    # mid-retry (CircuitOpenError). Both indicate the failure cascade was
    # detected and stopped — that's the contract.
    with pytest.raises((RetryError, CircuitOpenError)):
        await fn()
    # Breaker should be open after the cascade
    assert cb.is_open
