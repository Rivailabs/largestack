"""Per-tenant token + cost budget tracker (v0.10.0).

Critical for multi-tenant SaaS deployments: each tenant gets a budget
(daily / monthly / total), and the tracker enforces it. When a tenant
hits their cap, ``check_and_record`` raises ``BudgetExceededError`` —
upstream code converts that to HTTP 429 or similar.

Two storage backends:
- ``MemoryBudgetStore`` — in-process (single-host)
- ``RedisBudgetStore`` — Redis sliding-window counters
"""
from __future__ import annotations
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.budget")


class BudgetExceededError(Exception):
    """Raised when a tenant exceeds their budget."""
    def __init__(
        self, tenant_id: str, kind: str, used: float, limit: float,
    ):
        self.tenant_id = tenant_id
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(
            f"tenant {tenant_id!r}: {kind} budget exceeded — "
            f"used {used:.2f}, limit {limit:.2f}"
        )


@dataclass
class BudgetLimit:
    """A single budget limit (kind=tokens|cost_usd, window=day|month|total)."""
    tenant_id: str
    kind: str               # "tokens", "cost_usd"
    limit: float            # max value over the window
    window: str = "day"     # "day", "month", "total"

    def window_key(self) -> str:
        """Compute the current bucket key based on window."""
        now = time.time()
        if self.window == "day":
            day = int(now // 86400)
            return f"{self.tenant_id}:{self.kind}:day:{day}"
        if self.window == "month":
            import datetime as _dt
            now_d = _dt.datetime.fromtimestamp(now, _dt.timezone.utc)
            return f"{self.tenant_id}:{self.kind}:month:{now_d.year:04d}{now_d.month:02d}"
        return f"{self.tenant_id}:{self.kind}:total"


# -------------------- Storage backends --------------------

class BudgetStore(ABC):
    """ABC for budget counter storage."""

    @abstractmethod
    async def get(self, key: str) -> float:
        ...

    @abstractmethod
    async def add(self, key: str, value: float) -> float:
        ...

    @abstractmethod
    async def reset(self, key: str) -> None:
        ...


class MemoryBudgetStore(BudgetStore):
    """In-memory counter store. Loses data on restart."""

    def __init__(self):
        self._counters: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> float:
        async with self._lock:
            return self._counters.get(key, 0.0)

    async def add(self, key: str, value: float) -> float:
        async with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value
            return self._counters[key]

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._counters.pop(key, None)


class RedisBudgetStore(BudgetStore):
    """Redis-backed budget counter store with TTL on day/month buckets."""

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        *,
        prefix: str = "largestack:budget:",
        day_ttl: int = 90 * 86400,    # keep daily for 90 days
        month_ttl: int = 365 * 86400,  # keep monthly for 1 year
    ):
        self.url = url
        self.prefix = prefix
        self.day_ttl = day_ttl
        self.month_ttl = month_ttl
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            import redis.asyncio as redis_async
        except ImportError as e:
            raise ImportError(
                "RedisBudgetStore needs: pip install 'redis>=5.0'"
            ) from e
        self._client = redis_async.from_url(self.url, decode_responses=True)

    def _ttl_for_key(self, key: str) -> int | None:
        if ":day:" in key:
            return self.day_ttl
        if ":month:" in key:
            return self.month_ttl
        return None  # total budgets persist forever

    async def get(self, key: str) -> float:
        await self._connect()
        raw = await self._client.get(self.prefix + key)
        return float(raw) if raw else 0.0

    async def add(self, key: str, value: float) -> float:
        await self._connect()
        full_key = self.prefix + key
        new_val = await self._client.incrbyfloat(full_key, value)
        # Set TTL only if not already set
        ttl = self._ttl_for_key(key)
        if ttl:
            existing = await self._client.ttl(full_key)
            if existing < 0:  # -1 = no TTL
                await self._client.expire(full_key, ttl)
        return float(new_val)

    async def reset(self, key: str) -> None:
        await self._connect()
        await self._client.delete(self.prefix + key)


# -------------------- BudgetTracker --------------------

class BudgetTracker:
    """Per-tenant budget tracker.

    Args:
        store: backing ``BudgetStore``.
        limits: dict of ``{tenant_id: list[BudgetLimit]}``.

    Usage::

        tracker = BudgetTracker(MemoryBudgetStore(), {
            "acme": [
                BudgetLimit("acme", "tokens", 1_000_000, "day"),
                BudgetLimit("acme", "cost_usd", 50.0, "day"),
                BudgetLimit("acme", "cost_usd", 1000.0, "month"),
            ],
        })

        # Before each LLM call:
        await tracker.check_and_record("acme", tokens=2500, cost_usd=0.02)
    """

    def __init__(
        self,
        store: BudgetStore | None = None,
        limits: dict[str, list[BudgetLimit]] | None = None,
    ):
        self.store = store or MemoryBudgetStore()
        self.limits: dict[str, list[BudgetLimit]] = limits or {}

    def add_limit(self, limit: BudgetLimit) -> None:
        """Register a new limit for a tenant."""
        self.limits.setdefault(limit.tenant_id, []).append(limit)

    async def check_and_record(
        self,
        tenant_id: str,
        *,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> dict:
        """Atomically check + increment for all relevant limits.

        Args:
            tenant_id: tenant identifier
            tokens: number of tokens consumed
            cost_usd: dollar cost consumed

        Returns:
            Dict of ``{limit_kind_window: new_total}`` for all updated buckets.

        Raises:
            BudgetExceededError if any limit would be exceeded.
        """
        tenant_limits = self.limits.get(tenant_id, [])
        # Step 1: pre-check all limits to avoid partial increments
        for limit in tenant_limits:
            value_to_add = tokens if limit.kind == "tokens" else cost_usd
            if value_to_add <= 0:
                continue
            current = await self.store.get(limit.window_key())
            projected = current + value_to_add
            if projected > limit.limit:
                raise BudgetExceededError(
                    tenant_id, f"{limit.kind}.{limit.window}",
                    used=projected, limit=limit.limit,
                )

        # Step 2: increment all atomically
        results = {}
        for limit in tenant_limits:
            value_to_add = tokens if limit.kind == "tokens" else cost_usd
            if value_to_add <= 0:
                continue
            new_total = await self.store.add(limit.window_key(), value_to_add)
            results[f"{limit.kind}.{limit.window}"] = new_total

        return results

    async def get_usage(self, tenant_id: str) -> dict:
        """Get current usage across all limits."""
        tenant_limits = self.limits.get(tenant_id, [])
        out = {}
        for limit in tenant_limits:
            current = await self.store.get(limit.window_key())
            out[f"{limit.kind}.{limit.window}"] = {
                "used": current,
                "limit": limit.limit,
                "remaining": max(0.0, limit.limit - current),
                "exceeded": current > limit.limit,
            }
        return out

    async def reset_tenant(self, tenant_id: str) -> int:
        """Clear all counters for a tenant (e.g., manual override)."""
        tenant_limits = self.limits.get(tenant_id, [])
        for limit in tenant_limits:
            await self.store.reset(limit.window_key())
        return len(tenant_limits)
