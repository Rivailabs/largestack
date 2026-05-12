"""v0.10.0: Tests for per-tenant budget tracker."""
from __future__ import annotations

import pytest


# -------------------- MemoryBudgetStore --------------------

@pytest.mark.asyncio
async def test_memory_budget_store_basic():
    from largestack._core.budget import MemoryBudgetStore
    store = MemoryBudgetStore()
    assert await store.get("k") == 0.0
    new_val = await store.add("k", 5.0)
    assert new_val == 5.0
    assert await store.get("k") == 5.0
    new_val = await store.add("k", 3.5)
    assert new_val == 8.5


@pytest.mark.asyncio
async def test_memory_budget_store_reset():
    from largestack._core.budget import MemoryBudgetStore
    store = MemoryBudgetStore()
    await store.add("k", 10.0)
    await store.reset("k")
    assert await store.get("k") == 0.0


# -------------------- BudgetLimit --------------------

def test_budget_limit_window_key_for_day():
    from largestack._core.budget import BudgetLimit
    bl = BudgetLimit("tenant_a", "tokens", 1000.0, "day")
    key = bl.window_key()
    assert "tenant_a:tokens:day:" in key


def test_budget_limit_window_key_for_month():
    from largestack._core.budget import BudgetLimit
    bl = BudgetLimit("tenant_a", "cost_usd", 100.0, "month")
    key = bl.window_key()
    # Month format: YYYYMM
    assert "tenant_a:cost_usd:month:" in key
    # Should have 6 trailing digits (YYYYMM)
    suffix = key.split(":")[-1]
    assert len(suffix) == 6
    assert suffix.isdigit()


def test_budget_limit_window_key_for_total():
    from largestack._core.budget import BudgetLimit
    bl = BudgetLimit("tenant_a", "tokens", 999999.0, "total")
    assert bl.window_key() == "tenant_a:tokens:total"


# -------------------- BudgetTracker --------------------

@pytest.mark.asyncio
async def test_budget_tracker_records_usage():
    from largestack._core.budget import BudgetTracker, BudgetLimit
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("acme", "tokens", 1_000_000, "day"))

    result = await tracker.check_and_record("acme", tokens=5000)
    assert result["tokens.day"] == 5000

    # Cumulative
    result = await tracker.check_and_record("acme", tokens=3000)
    assert result["tokens.day"] == 8000


@pytest.mark.asyncio
async def test_budget_tracker_raises_when_exceeded():
    from largestack._core.budget import (
        BudgetTracker, BudgetLimit, BudgetExceededError,
    )
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("small", "tokens", 1000, "day"))

    await tracker.check_and_record("small", tokens=900)
    with pytest.raises(BudgetExceededError) as exc:
        await tracker.check_and_record("small", tokens=200)
    assert exc.value.tenant_id == "small"
    assert exc.value.kind == "tokens.day"


@pytest.mark.asyncio
async def test_budget_tracker_atomic_no_partial_increment():
    """If any limit would be exceeded, NO counters increment."""
    from largestack._core.budget import (
        BudgetTracker, BudgetLimit, BudgetExceededError,
    )
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("acme", "tokens", 100_000, "day"))
    tracker.add_limit(BudgetLimit("acme", "cost_usd", 10.0, "day"))

    # First call succeeds
    await tracker.check_and_record("acme", tokens=50_000, cost_usd=5.0)

    # This call would exceed cost_usd budget
    with pytest.raises(BudgetExceededError):
        await tracker.check_and_record("acme", tokens=10_000, cost_usd=6.0)

    # Verify tokens counter did NOT increment from the rejected call
    usage = await tracker.get_usage("acme")
    assert usage["tokens.day"]["used"] == 50_000  # unchanged
    assert usage["cost_usd.day"]["used"] == 5.0   # unchanged


@pytest.mark.asyncio
async def test_budget_tracker_multiple_windows():
    from largestack._core.budget import BudgetTracker, BudgetLimit, BudgetExceededError
    tracker = BudgetTracker()
    # Daily limit smaller than monthly
    tracker.add_limit(BudgetLimit("t", "tokens", 100, "day"))
    tracker.add_limit(BudgetLimit("t", "tokens", 10000, "month"))

    await tracker.check_and_record("t", tokens=50)
    await tracker.check_and_record("t", tokens=40)
    # Total 90, hitting day limit of 100 with another 50 would exceed
    with pytest.raises(BudgetExceededError) as exc:
        await tracker.check_and_record("t", tokens=50)
    assert exc.value.kind == "tokens.day"


@pytest.mark.asyncio
async def test_budget_tracker_get_usage():
    from largestack._core.budget import BudgetTracker, BudgetLimit
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("t", "tokens", 1000, "day"))
    tracker.add_limit(BudgetLimit("t", "cost_usd", 5.0, "day"))

    await tracker.check_and_record("t", tokens=300, cost_usd=1.5)

    usage = await tracker.get_usage("t")
    assert usage["tokens.day"]["used"] == 300
    assert usage["tokens.day"]["remaining"] == 700
    assert usage["tokens.day"]["exceeded"] is False
    assert usage["cost_usd.day"]["used"] == 1.5


@pytest.mark.asyncio
async def test_budget_tracker_reset_tenant():
    from largestack._core.budget import BudgetTracker, BudgetLimit
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("t", "tokens", 1000, "day"))
    await tracker.check_and_record("t", tokens=500)
    n = await tracker.reset_tenant("t")
    assert n == 1
    usage = await tracker.get_usage("t")
    assert usage["tokens.day"]["used"] == 0


@pytest.mark.asyncio
async def test_budget_tracker_unknown_tenant_no_op():
    """Unknown tenant has no limits → no enforcement."""
    from largestack._core.budget import BudgetTracker
    tracker = BudgetTracker()
    # Should not raise
    result = await tracker.check_and_record("unknown_tenant", tokens=99999999)
    assert result == {}


@pytest.mark.asyncio
async def test_budget_tracker_zero_values_dont_increment():
    from largestack._core.budget import BudgetTracker, BudgetLimit
    tracker = BudgetTracker()
    tracker.add_limit(BudgetLimit("t", "tokens", 1000, "day"))
    await tracker.check_and_record("t", tokens=0)
    usage = await tracker.get_usage("t")
    assert usage["tokens.day"]["used"] == 0


# -------------------- RedisBudgetStore --------------------

@pytest.mark.asyncio
async def test_redis_budget_store_handles_missing_redis():
    from largestack._core.budget import RedisBudgetStore
    import sys
    saved = sys.modules.pop("redis", None)
    saved_async = sys.modules.pop("redis.asyncio", None)
    sys.modules["redis"] = None
    sys.modules["redis.asyncio"] = None
    try:
        store = RedisBudgetStore()
        with pytest.raises(ImportError, match="redis"):
            await store.get("k")
    finally:
        if saved is not None:
            sys.modules["redis"] = saved
        else:
            sys.modules.pop("redis", None)
        if saved_async is not None:
            sys.modules["redis.asyncio"] = saved_async
        else:
            sys.modules.pop("redis.asyncio", None)
