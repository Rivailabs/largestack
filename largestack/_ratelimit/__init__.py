"""Per-tenant rate limiting (v0.13.0).

Closes the SaaS-readiness gap. Token-bucket rate limiter with per-tenant
isolation. Use cases:

- "tenant A: 100 req/sec, tenant B: 1000 req/sec" SLA tiers
- Block runaway agents from one tenant from starving others
- Per-LLM-provider sub-limits (OpenAI, Bedrock, Azure)

Two backends:

- ``InMemoryRateLimiter`` — single-process, zero-deps, works in dev
- ``RedisRateLimiter`` — multi-process / multi-region (atomic via
  Redis Lua script), production-grade

Both implement the same async interface::

    limiter = InMemoryRateLimiter()
    limiter.set_quota("tenant_a", rate_per_sec=100, burst=200)
    allowed = await limiter.try_acquire("tenant_a", cost=1)
    if not allowed:
        raise RateLimitExceeded("tenant_a")
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Protocol

log = logging.getLogger("largestack.ratelimit")


class RateLimitExceeded(Exception):
    """Raised when a tenant exceeds its quota."""

    def __init__(self, tenant_id: str, retry_after: float = 1.0):
        super().__init__(
            f"rate limit exceeded for tenant '{tenant_id}'; "
            f"retry after {retry_after:.2f}s"
        )
        self.tenant_id = tenant_id
        self.retry_after = retry_after


@dataclass
class TenantQuota:
    """Token-bucket parameters for a tenant."""
    rate_per_sec: float  # token replenishment rate
    burst: float         # max bucket size
    label: str = ""

    def __post_init__(self):
        if self.rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be positive")
        if self.burst <= 0:
            raise ValueError("burst must be positive")


@dataclass
class _Bucket:
    """Internal bucket state for one (tenant, key) pair."""
    tokens: float
    last_refill: float

    def refill(self, now: float, quota: TenantQuota) -> None:
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(
            quota.burst,
            self.tokens + elapsed * quota.rate_per_sec,
        )
        self.last_refill = now


class RateLimiterProtocol(Protocol):
    """Common interface for all rate limiter backends."""

    def set_quota(
        self, tenant_id: str, *, rate_per_sec: float, burst: float,
    ) -> None: ...

    async def try_acquire(
        self, tenant_id: str, *, cost: float = 1.0, key: str = "default",
    ) -> bool: ...

    async def acquire(
        self,
        tenant_id: str,
        *,
        cost: float = 1.0,
        key: str = "default",
        timeout: float | None = None,
    ) -> None: ...

    async def get_remaining(
        self, tenant_id: str, *, key: str = "default",
    ) -> float: ...


# -------------------- In-memory implementation --------------------

class InMemoryRateLimiter:
    """Single-process token-bucket limiter with per-tenant isolation.

    Args:
        default_quota: applied to tenants without an explicit quota
    """

    def __init__(
        self,
        default_quota: TenantQuota | None = None,
    ):
        self._quotas: dict[str, TenantQuota] = {}
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._default = default_quota or TenantQuota(
            rate_per_sec=10.0, burst=20.0, label="default",
        )
        self._lock = asyncio.Lock()

    def set_quota(
        self,
        tenant_id: str,
        *,
        rate_per_sec: float,
        burst: float,
        label: str = "",
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self._quotas[tenant_id] = TenantQuota(
            rate_per_sec=rate_per_sec, burst=burst,
            label=label or tenant_id,
        )

    def _quota_for(self, tenant_id: str) -> TenantQuota:
        return self._quotas.get(tenant_id, self._default)

    async def try_acquire(
        self,
        tenant_id: str,
        *,
        cost: float = 1.0,
        key: str = "default",
    ) -> bool:
        """Atomically attempt to consume ``cost`` tokens. Returns True on success."""
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if cost < 0:
            raise ValueError("cost must be non-negative")

        quota = self._quota_for(tenant_id)
        bucket_key = (tenant_id, key)

        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = _Bucket(tokens=quota.burst, last_refill=now)
                self._buckets[bucket_key] = bucket
            bucket.refill(now, quota)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            return False

    async def acquire(
        self,
        tenant_id: str,
        *,
        cost: float = 1.0,
        key: str = "default",
        timeout: float | None = None,
    ) -> None:
        """Wait until ``cost`` tokens are available, or raise ``TimeoutError``."""
        deadline = (time.monotonic() + timeout) if timeout else None
        while True:
            if await self.try_acquire(tenant_id, cost=cost, key=key):
                return
            quota = self._quota_for(tenant_id)
            wait = max(0.05, cost / quota.rate_per_sec)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"rate limit acquire timeout for {tenant_id}"
                    )
                wait = min(wait, remaining)
            await asyncio.sleep(wait)

    async def get_remaining(
        self,
        tenant_id: str,
        *,
        key: str = "default",
    ) -> float:
        """Returns current bucket level (informational; non-locking)."""
        quota = self._quota_for(tenant_id)
        bucket = self._buckets.get((tenant_id, key))
        if bucket is None:
            return quota.burst
        async with self._lock:
            bucket.refill(time.monotonic(), quota)
            return bucket.tokens

    async def reset(self, tenant_id: str) -> None:
        """Clear all buckets for a tenant. Useful for testing."""
        async with self._lock:
            keys = [k for k in self._buckets if k[0] == tenant_id]
            for k in keys:
                del self._buckets[k]


# -------------------- Redis implementation --------------------

# Lua: atomic refill + consume in one round-trip
_REDIS_LUA_ACQUIRE = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
  tokens = burst
  last_refill = now
end

local elapsed = math.max(0, now - last_refill)
tokens = math.min(burst, tokens + elapsed * rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', key, 3600)

return {allowed, tokens}
"""


class RedisRateLimiter:
    """Multi-process / multi-region token-bucket via Redis.

    Atomicity via Lua script. Key pattern: ``largestack:rl:{tenant_id}:{key}``.

    Args:
        redis_client: ``redis.asyncio.Redis`` instance (caller-provided)
        default_quota: fallback for tenants without explicit quota
        key_prefix: optional namespace for the Redis keys
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        default_quota: TenantQuota | None = None,
        key_prefix: str = "largestack:rl",
    ):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self._quotas: dict[str, TenantQuota] = {}
        self._default = default_quota or TenantQuota(
            rate_per_sec=10.0, burst=20.0, label="default",
        )
        self._sha: str | None = None

    def set_quota(
        self,
        tenant_id: str,
        *,
        rate_per_sec: float,
        burst: float,
        label: str = "",
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self._quotas[tenant_id] = TenantQuota(
            rate_per_sec=rate_per_sec, burst=burst,
            label=label or tenant_id,
        )

    def _quota_for(self, tenant_id: str) -> TenantQuota:
        return self._quotas.get(tenant_id, self._default)

    def _redis_key(self, tenant_id: str, key: str) -> str:
        return f"{self.key_prefix}:{tenant_id}:{key}"

    async def _ensure_script(self) -> None:
        if self._sha is None:
            self._sha = await self.redis.script_load(_REDIS_LUA_ACQUIRE)

    async def try_acquire(
        self,
        tenant_id: str,
        *,
        cost: float = 1.0,
        key: str = "default",
    ) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        await self._ensure_script()
        quota = self._quota_for(tenant_id)
        result = await self.redis.evalsha(
            self._sha,
            1,
            self._redis_key(tenant_id, key),
            quota.rate_per_sec, quota.burst, cost, time.time(),
        )
        # Lua returns [allowed, tokens]
        return int(result[0]) == 1

    async def acquire(
        self,
        tenant_id: str,
        *,
        cost: float = 1.0,
        key: str = "default",
        timeout: float | None = None,
    ) -> None:
        deadline = (time.monotonic() + timeout) if timeout else None
        while True:
            if await self.try_acquire(tenant_id, cost=cost, key=key):
                return
            quota = self._quota_for(tenant_id)
            wait = max(0.05, cost / quota.rate_per_sec)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"rate limit acquire timeout for {tenant_id}"
                    )
                wait = min(wait, remaining)
            await asyncio.sleep(wait)

    async def get_remaining(
        self, tenant_id: str, *, key: str = "default",
    ) -> float:
        quota = self._quota_for(tenant_id)
        data = await self.redis.hmget(
            self._redis_key(tenant_id, key),
            "tokens", "last_refill",
        )
        tokens = float(data[0]) if data[0] is not None else quota.burst
        last = float(data[1]) if data[1] is not None else time.time()
        elapsed = max(0.0, time.time() - last)
        return min(quota.burst, tokens + elapsed * quota.rate_per_sec)


__all__ = [
    "RateLimitExceeded",
    "TenantQuota",
    "RateLimiterProtocol",
    "InMemoryRateLimiter",
    "RedisRateLimiter",
]
