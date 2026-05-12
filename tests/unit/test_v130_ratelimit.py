"""v0.13.0: Tests for per-tenant rate limiter."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Module + types --------------------

def test_module_imports():
    from largestack._ratelimit import (
        InMemoryRateLimiter, RedisRateLimiter, TenantQuota,
        RateLimitExceeded,
    )
    assert InMemoryRateLimiter is not None
    assert RedisRateLimiter is not None
    assert issubclass(RateLimitExceeded, Exception)


def test_quota_validates_positive_rate():
    from largestack._ratelimit import TenantQuota
    with pytest.raises(ValueError, match="rate_per_sec"):
        TenantQuota(rate_per_sec=0, burst=10)
    with pytest.raises(ValueError, match="rate_per_sec"):
        TenantQuota(rate_per_sec=-1, burst=10)


def test_quota_validates_positive_burst():
    from largestack._ratelimit import TenantQuota
    with pytest.raises(ValueError, match="burst"):
        TenantQuota(rate_per_sec=1, burst=0)


def test_rate_limit_exceeded_carries_tenant():
    from largestack._ratelimit import RateLimitExceeded
    e = RateLimitExceeded("alice", retry_after=2.5)
    assert e.tenant_id == "alice"
    assert e.retry_after == 2.5


# -------------------- InMemoryRateLimiter --------------------

@pytest.mark.asyncio
async def test_in_memory_basic_acquire():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=10.0, burst=5.0)

    # Burst: 5 tokens available immediately
    for _ in range(5):
        assert await rl.try_acquire("alice")

    # Sixth should fail (within same instant)
    assert not await rl.try_acquire("alice")


@pytest.mark.asyncio
async def test_in_memory_isolates_tenants():
    """One tenant's exhaustion must not affect another."""
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=1.0, burst=2.0)
    rl.set_quota("bob",   rate_per_sec=1.0, burst=2.0)

    # Drain alice
    assert await rl.try_acquire("alice")
    assert await rl.try_acquire("alice")
    assert not await rl.try_acquire("alice")

    # Bob still has full quota
    assert await rl.try_acquire("bob")
    assert await rl.try_acquire("bob")


@pytest.mark.asyncio
async def test_in_memory_default_quota_for_unknown_tenant():
    from largestack._ratelimit import InMemoryRateLimiter, TenantQuota

    rl = InMemoryRateLimiter(
        default_quota=TenantQuota(rate_per_sec=1.0, burst=3.0),
    )
    # Unknown tenant uses default
    for _ in range(3):
        assert await rl.try_acquire("unknown")
    assert not await rl.try_acquire("unknown")


@pytest.mark.asyncio
async def test_in_memory_refills_over_time():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    # Very high rate so refill happens during sleep
    rl.set_quota("alice", rate_per_sec=20.0, burst=1.0)

    assert await rl.try_acquire("alice")
    assert not await rl.try_acquire("alice")

    # Wait long enough for refill
    await asyncio.sleep(0.15)  # 0.15 * 20 = 3 tokens, capped at burst=1
    assert await rl.try_acquire("alice")


@pytest.mark.asyncio
async def test_in_memory_get_remaining_starts_at_burst():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=1.0, burst=10.0)
    remaining = await rl.get_remaining("alice")
    assert remaining == 10.0


@pytest.mark.asyncio
async def test_in_memory_get_remaining_decreases_after_acquire():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=1.0, burst=10.0)
    await rl.try_acquire("alice", cost=3.0)
    remaining = await rl.get_remaining("alice")
    assert 6.9 <= remaining <= 7.1  # ~7 modulo small refill


@pytest.mark.asyncio
async def test_in_memory_acquire_blocks_then_succeeds():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=20.0, burst=1.0)

    assert await rl.try_acquire("alice")
    # Bucket is empty; acquire() should wait + succeed
    start = time.monotonic()
    await rl.acquire("alice", timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed < 1.5  # well under timeout


@pytest.mark.asyncio
async def test_in_memory_acquire_times_out():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=0.5, burst=1.0)
    await rl.try_acquire("alice")  # drain

    with pytest.raises(TimeoutError):
        await rl.acquire("alice", cost=10.0, timeout=0.1)


@pytest.mark.asyncio
async def test_in_memory_separate_keys_per_tenant():
    """A tenant can have separate buckets per key (e.g. per-LLM-provider)."""
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=1.0, burst=2.0)

    # Burn through 'openai' key
    assert await rl.try_acquire("alice", key="openai")
    assert await rl.try_acquire("alice", key="openai")
    assert not await rl.try_acquire("alice", key="openai")

    # 'bedrock' key has full quota
    assert await rl.try_acquire("alice", key="bedrock")


@pytest.mark.asyncio
async def test_in_memory_set_quota_requires_tenant():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    with pytest.raises(ValueError, match="tenant_id"):
        rl.set_quota("", rate_per_sec=1, burst=1)


@pytest.mark.asyncio
async def test_in_memory_try_acquire_requires_tenant():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    with pytest.raises(ValueError, match="tenant_id"):
        await rl.try_acquire("")


@pytest.mark.asyncio
async def test_in_memory_reset_clears_buckets():
    from largestack._ratelimit import InMemoryRateLimiter

    rl = InMemoryRateLimiter()
    rl.set_quota("alice", rate_per_sec=1.0, burst=2.0)
    await rl.try_acquire("alice")
    await rl.try_acquire("alice")
    assert not await rl.try_acquire("alice")

    await rl.reset("alice")
    # After reset, full burst available again
    assert await rl.try_acquire("alice")


# -------------------- RedisRateLimiter --------------------

@pytest.mark.asyncio
async def test_redis_limiter_invokes_lua_script():
    from largestack._ratelimit import RedisRateLimiter

    fake_redis = MagicMock()
    fake_redis.script_load = AsyncMock(return_value="abc123")
    fake_redis.evalsha = AsyncMock(return_value=[1, 9.0])

    rl = RedisRateLimiter(fake_redis)
    rl.set_quota("alice", rate_per_sec=10.0, burst=10.0)

    ok = await rl.try_acquire("alice")
    assert ok
    fake_redis.script_load.assert_called_once()
    fake_redis.evalsha.assert_called_once()


@pytest.mark.asyncio
async def test_redis_limiter_returns_false_when_lua_says_no():
    from largestack._ratelimit import RedisRateLimiter

    fake_redis = MagicMock()
    fake_redis.script_load = AsyncMock(return_value="sha1")
    fake_redis.evalsha = AsyncMock(return_value=[0, 0.5])  # not allowed

    rl = RedisRateLimiter(fake_redis)
    rl.set_quota("alice", rate_per_sec=1.0, burst=1.0)
    ok = await rl.try_acquire("alice")
    assert not ok


@pytest.mark.asyncio
async def test_redis_limiter_keys_namespaced():
    from largestack._ratelimit import RedisRateLimiter

    fake_redis = MagicMock()
    fake_redis.script_load = AsyncMock(return_value="sha")
    fake_redis.evalsha = AsyncMock(return_value=[1, 5.0])

    rl = RedisRateLimiter(fake_redis, key_prefix="my-app:rl")
    rl.set_quota("alice", rate_per_sec=1.0, burst=10.0)
    await rl.try_acquire("alice", key="openai")

    args = fake_redis.evalsha.call_args[0]
    # args = (sha, num_keys, key, rate, burst, cost, now)
    redis_key = args[2]
    assert redis_key == "my-app:rl:alice:openai"


@pytest.mark.asyncio
async def test_redis_limiter_get_remaining_handles_unset_key():
    from largestack._ratelimit import RedisRateLimiter

    fake_redis = MagicMock()
    fake_redis.hmget = AsyncMock(return_value=[None, None])
    fake_redis.script_load = AsyncMock(return_value="sha")

    rl = RedisRateLimiter(fake_redis)
    rl.set_quota("alice", rate_per_sec=1.0, burst=10.0)
    remaining = await rl.get_remaining("alice")
    # Unset → return burst
    assert remaining == 10.0
