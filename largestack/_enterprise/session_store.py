"""Session store — pluggable backend for SSO sessions (v0.5.0).

Two backends:

- **InMemorySessionStore** (default): per-worker dict. Fast, zero deps.
  Each worker has its own state — sessions don't survive worker restart
  or load across replicas. Adequate for single-process / dev / test.

- **RedisSessionStore**: distributed via Redis with native TTL. Sessions
  survive process restarts, work across multiple workers, and are
  automatically expired by Redis. Set ``LARGESTACK_SESSION_BACKEND=redis``
  and ``LARGESTACK_REDIS_URL=redis://...``.

This solves the "in-memory = multi-worker breaks" gap from v0.4.0.
The store interface is sync since session lookup is on the hot path of
every authenticated request and we don't want to force `await` everywhere
the SSO provider is used. For Redis, this means we use the synchronous
`redis-py` client (still fast enough — <1ms per op on local Redis).
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from typing import Protocol

log = logging.getLogger("largestack.session_store")


class _SessionLike(Protocol):
    """Duck-typed session — anything with these attributes works."""
    session_id: str
    user_info: dict
    created_at: float
    ttl: float
    last_active: float
    refresh_token: str | None

    def to_dict(self) -> dict: ...


class SessionStore:
    """Abstract base. Concrete: InMemorySessionStore, RedisSessionStore."""

    def get(self, session_id: str) -> _SessionLike | None:
        raise NotImplementedError

    def put(self, session: _SessionLike) -> None:
        raise NotImplementedError

    def delete(self, session_id: str) -> bool:
        raise NotImplementedError

    def cleanup_expired(self) -> int:
        """Returns number of sessions removed."""
        raise NotImplementedError

    def all(self) -> list[_SessionLike]:
        """For admin / metrics. May be slow on Redis with many keys."""
        raise NotImplementedError

    def backend_name(self) -> str:
        return "abstract"


# --------------------------------------------------------------------------
# In-memory backend (legacy v0.4 behavior)
# --------------------------------------------------------------------------

class InMemorySessionStore(SessionStore):
    """Per-worker dict. Default backend."""

    def __init__(self):
        self._sessions: dict[str, _SessionLike] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> _SessionLike | None:
        with self._lock:
            s = self._sessions.get(session_id)
        if s is None:
            return None
        # Expire on read
        if hasattr(s, "is_expired") and s.is_expired:
            with self._lock:
                self._sessions.pop(session_id, None)
            return None
        return s

    def put(self, session: _SessionLike) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if hasattr(s, "is_expired") and s.is_expired
            ]
            for sid in expired:
                del self._sessions[sid]
        return len(expired)

    def all(self) -> list[_SessionLike]:
        with self._lock:
            return list(self._sessions.values())

    def backend_name(self) -> str:
        return "inmemory"


# --------------------------------------------------------------------------
# Redis backend (production multi-worker)
# --------------------------------------------------------------------------

class RedisSessionStore(SessionStore):
    """Distributed sessions via Redis. Falls back to in-memory on connect failure.

    Storage:
      - Each session at key ``largestack:sess:{session_id}`` with native TTL.
      - JSON-serialized session.to_dict() format.
      - Session class must accept ``Session.from_dict(d)`` on read.

    Note: requires `pip install redis`. Without it, falls back to in-memory.
    """

    def __init__(
        self,
        redis_url: str,
        session_factory=None,
        prefix: str = "largestack:sess:",
    ):
        """
        Args:
            redis_url: e.g. ``redis://localhost:6379/0``
            session_factory: callable ``(dict) -> Session``. If None, uses
                the SSO module's ``Session`` class via lazy import.
            prefix: Redis key prefix for sessions.
        """
        self.prefix = prefix
        self.fallback = InMemorySessionStore()
        self._redis = None
        self._session_factory = session_factory
        self._connect(redis_url)

    def _connect(self, redis_url: str) -> None:
        try:
            import redis  # type: ignore
        except ImportError:
            log.warning(
                "LARGESTACK_SESSION_BACKEND=redis but `redis` package not installed. "
                "Run: pip install redis. Falling back to in-memory store."
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
            self._redis = client
            log.info(f"SessionStore: redis backend connected ({redis_url})")
        except Exception as e:
            log.warning(
                f"Redis session store unavailable ({e}). "
                "Falling back to in-memory — sessions will NOT survive restart "
                "or scale across workers until Redis is reachable."
            )
            self._redis = None

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def _factory(self):
        """Lazy-load Session class to avoid import cycle."""
        if self._session_factory is not None:
            return self._session_factory
        from largestack._enterprise.sso import Session

        def _make(d: dict):
            s = Session(
                session_id=d["session_id"],
                user_info=d["user_info"],
                ttl=d.get("ttl", 3600),
            )
            s.created_at = d.get("created_at", time.time())
            s.last_active = d.get("last_active", time.time())
            s.refresh_token = d.get("refresh_token")
            return s
        return _make

    def get(self, session_id: str) -> _SessionLike | None:
        if self._redis is None:
            return self.fallback.get(session_id)
        try:
            raw = self._redis.get(self._key(session_id))
        except Exception as e:
            log.debug(f"redis get failed: {e}; using fallback")
            return self.fallback.get(session_id)
        if raw is None:
            return None
        try:
            d = json.loads(raw)
            return self._factory()(d)
        except Exception as e:
            log.warning(f"corrupt session data for {session_id}: {e}")
            return None

    def put(self, session: _SessionLike) -> None:
        if self._redis is None:
            self.fallback.put(session)
            return
        try:
            ttl = max(int(session.ttl), 1)  # Redis EX needs >= 1
            payload = json.dumps(session.to_dict())
            self._redis.set(self._key(session.session_id), payload, ex=ttl)
        except Exception as e:
            log.warning(f"redis put failed: {e}; using fallback")
            self.fallback.put(session)

    def delete(self, session_id: str) -> bool:
        if self._redis is None:
            return self.fallback.delete(session_id)
        try:
            return bool(self._redis.delete(self._key(session_id)))
        except Exception as e:
            log.debug(f"redis delete failed: {e}")
            return self.fallback.delete(session_id)

    def cleanup_expired(self) -> int:
        # Redis does this automatically via TTL — no-op
        if self._redis is None:
            return self.fallback.cleanup_expired()
        return 0

    def all(self) -> list[_SessionLike]:
        if self._redis is None:
            return self.fallback.all()
        try:
            keys = list(self._redis.scan_iter(match=f"{self.prefix}*", count=200))
        except Exception as e:
            log.debug(f"redis scan failed: {e}")
            return self.fallback.all()

        sessions: list[_SessionLike] = []
        factory = self._factory()
        for k in keys[:1000]:  # cap at 1k for safety
            try:
                raw = self._redis.get(k)
                if raw:
                    sessions.append(factory(json.loads(raw)))
            except Exception:
                continue
        return sessions

    def backend_name(self) -> str:
        return "redis" if self._redis is not None else "inmemory(fallback)"


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

def create_session_store() -> SessionStore:
    """Create a session store based on env vars.

    Env vars:
      - LARGESTACK_SESSION_BACKEND: ``inmemory`` (default) or ``redis``
      - LARGESTACK_REDIS_URL: e.g. ``redis://localhost:6379/0``
    """
    backend = os.environ.get("LARGESTACK_SESSION_BACKEND", "inmemory").lower()
    if backend == "redis":
        url = os.environ.get("LARGESTACK_REDIS_URL", "redis://localhost:6379/0")
        return RedisSessionStore(redis_url=url)
    return InMemorySessionStore()
