"""Rate limiter for serve & dashboard endpoints (v0.4.0).

Two backends:

  - **in-process** (default): per-worker token bucket. Fast, zero deps.
    Each worker has its own state — global limit = N_workers × limit.
    Adequate for single-process or trusted-input deployments.

  - **redis**: per-key token bucket via Redis Lua script. Truly distributed.
    Set ``LARGESTACK_RATE_LIMIT_BACKEND=redis`` and ``LARGESTACK_REDIS_URL=redis://...``.
    Fails gracefully to in-process if Redis is unreachable (logs WARNING).

Configuration env vars:
  - ``LARGESTACK_RATE_LIMIT_BACKEND``: ``inprocess`` (default) or ``redis``
  - ``LARGESTACK_RATE_LIMIT_PER_MINUTE``: default 60
  - ``LARGESTACK_RATE_LIMIT_BURST``: default 10
  - ``LARGESTACK_RATE_LIMIT_DISABLE``: ``1`` bypasses entirely
  - ``LARGESTACK_REDIS_URL``: e.g. ``redis://localhost:6379/0``

Usage in FastAPI:

    from largestack._dashboard.rate_limit import rate_limit_dependency
    @app.get("/api/foo", dependencies=[Depends(rate_limit_dependency)])
"""

from __future__ import annotations
import logging
import os
import threading
import time
from collections import OrderedDict

from fastapi import Request

log = logging.getLogger("largestack.rate_limit")


# --------------------------------------------------------------------------
# In-process backend (token bucket)
# --------------------------------------------------------------------------


class _Bucket:
    """Token bucket with continuous refill."""

    __slots__ = ("tokens", "last_refill", "capacity", "refill_per_sec")

    def __init__(self, capacity: int, refill_per_sec: float):
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.capacity = float(capacity)
        self.refill_per_sec = refill_per_sec

    def consume(self, n: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class InProcessRateLimiter:
    """Per-key LRU-bounded rate limiter. Single-process only."""

    def __init__(self, per_minute: int = 60, burst: int = 10, max_keys: int = 10_000):
        self.refill_per_sec = per_minute / 60.0
        self.burst = burst
        self.max_keys = max_keys
        self._buckets: "OrderedDict[str, _Bucket]" = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str, cost: float = 1.0) -> bool:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self.burst, self.refill_per_sec)
                self._buckets[key] = bucket
                while len(self._buckets) > self.max_keys:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
            return bucket.consume(cost)

    def backend_name(self) -> str:
        return "inprocess"


# --------------------------------------------------------------------------
# Redis backend (distributed)
# --------------------------------------------------------------------------

# Lua script: atomic token-bucket. Returns 1 if allowed, 0 if rate-limited.
# Stored fields: tokens (float), ts (float monotonic-ish, server time)
_REDIS_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_per_sec = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)
local allowed = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)
return allowed
"""


class RedisRateLimiter:
    """Distributed token-bucket via Redis. Falls back to in-process on error."""

    def __init__(self, redis_url: str, per_minute: int = 60, burst: int = 10):
        self.refill_per_sec = per_minute / 60.0
        self.burst = burst
        self.fallback = InProcessRateLimiter(per_minute=per_minute, burst=burst)
        self._lua_sha: str | None = None
        self._redis = None
        self._connect(redis_url)

    def _connect(self, redis_url: str) -> None:
        try:
            import redis  # type: ignore
        except ImportError:
            log.warning(
                "LARGESTACK_RATE_LIMIT_BACKEND=redis but `redis` package is not installed. "
                "Run: pip install redis. Falling back to in-process limiter."
            )
            return
        try:
            client = redis.Redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            client.ping()
            self._lua_sha = client.script_load(_REDIS_LUA)
            self._redis = client
            log.info(f"RateLimiter: redis backend connected ({redis_url})")
        except Exception as e:
            log.warning(
                f"Redis rate limiter unavailable ({e}). "
                "Falling back to in-process limiter for THIS worker only — "
                "the global rate limit is not enforced across workers until "
                "Redis is reachable."
            )
            self._redis = None

    def check(self, key: str, cost: float = 1.0) -> bool:
        if self._redis is None or self._lua_sha is None:
            return self.fallback.check(key, cost)
        try:
            result = self._redis.evalsha(
                self._lua_sha,
                1,
                f"largestack:rl:{key}",
                str(time.time()),
                str(self.burst),
                str(self.refill_per_sec),
                str(cost),
                "120",  # TTL: 2 min after last request
            )
            return bool(int(result))
        except Exception as e:
            # Hot-path failures fall back without spamming logs.
            log.debug(f"redis rate-limit check failed: {e}; using fallback")
            return self.fallback.check(key, cost)

    def backend_name(self) -> str:
        return "redis" if self._redis is not None else "inprocess(fallback)"


# --------------------------------------------------------------------------
# Singleton + factory
# --------------------------------------------------------------------------

_limiter_singleton: InProcessRateLimiter | RedisRateLimiter | None = None
_limiter_lock = threading.Lock()


def _get_limiter() -> InProcessRateLimiter | RedisRateLimiter:
    global _limiter_singleton
    if _limiter_singleton is not None:
        return _limiter_singleton
    with _limiter_lock:
        if _limiter_singleton is None:
            per_min = int(os.environ.get("LARGESTACK_RATE_LIMIT_PER_MINUTE", "60"))
            burst = int(os.environ.get("LARGESTACK_RATE_LIMIT_BURST", "10"))
            backend = os.environ.get("LARGESTACK_RATE_LIMIT_BACKEND", "inprocess").lower()
            if backend == "redis":
                redis_url = os.environ.get("LARGESTACK_REDIS_URL", "redis://localhost:6379/0")
                _limiter_singleton = RedisRateLimiter(
                    redis_url=redis_url, per_minute=per_min, burst=burst
                )
            else:
                _limiter_singleton = InProcessRateLimiter(per_minute=per_min, burst=burst)
                log.info(f"RateLimiter: inprocess backend, {per_min}/min burst={burst}")
    return _limiter_singleton


def reset_for_tests() -> None:
    """Reset the singleton — for unit tests only."""
    global _limiter_singleton
    with _limiter_lock:
        _limiter_singleton = None


def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency. Raises HTTPException(429) when limit exceeded.

    Key derivation order:
      1. ``X-API-Key`` header (per-key limit)
      2. ``X-Forwarded-For`` first IP (behind proxy)
      3. ``request.client.host``
    """
    if os.environ.get("LARGESTACK_RATE_LIMIT_DISABLE", "").lower() in ("1", "true", "yes"):
        return
    from fastapi import HTTPException

    key = (
        request.headers.get("X-API-Key")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if getattr(request, "client", None) else "unknown")
    )
    if not _get_limiter().check(key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down.",
            headers={"Retry-After": "60"},
        )


# Backwards-compat alias — old code referenced `RateLimiter`.
RateLimiter = InProcessRateLimiter
