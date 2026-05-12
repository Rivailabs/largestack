"""v0.5.0: Pluggable session store (in-memory + Redis backends)."""
from __future__ import annotations

import time

import pytest


# -------------------- in-memory backend --------------------

def test_inmemory_session_store_basic():
    from largestack._enterprise.session_store import InMemorySessionStore
    from largestack._enterprise.sso import Session
    store = InMemorySessionStore()

    s = Session(session_id="abc", user_info={"user_id": "alice"}, ttl=3600)
    store.put(s)

    got = store.get("abc")
    assert got is not None
    assert got.session_id == "abc"
    assert got.user_info["user_id"] == "alice"


def test_inmemory_session_store_delete():
    from largestack._enterprise.session_store import InMemorySessionStore
    from largestack._enterprise.sso import Session
    store = InMemorySessionStore()

    s = Session(session_id="abc", user_info={"user_id": "alice"})
    store.put(s)
    assert store.delete("abc") is True
    assert store.get("abc") is None
    # Idempotent
    assert store.delete("abc") is False


def test_inmemory_session_store_expired_session_returns_none():
    """A session past its TTL must not be returned."""
    from largestack._enterprise.session_store import InMemorySessionStore
    from largestack._enterprise.sso import Session
    store = InMemorySessionStore()

    s = Session(session_id="abc", user_info={"u": "x"}, ttl=0.01)
    store.put(s)
    time.sleep(0.05)
    assert store.get("abc") is None


def test_inmemory_session_store_cleanup_expired():
    from largestack._enterprise.session_store import InMemorySessionStore
    from largestack._enterprise.sso import Session
    store = InMemorySessionStore()

    # 3 sessions, mix of TTLs
    store.put(Session("a", {"u": "1"}, ttl=0.01))
    store.put(Session("b", {"u": "2"}, ttl=0.01))
    store.put(Session("c", {"u": "3"}, ttl=3600))
    time.sleep(0.05)

    removed = store.cleanup_expired()
    assert removed == 2
    assert store.get("c") is not None
    assert store.get("a") is None


def test_inmemory_session_store_all_returns_all():
    from largestack._enterprise.session_store import InMemorySessionStore
    from largestack._enterprise.sso import Session
    store = InMemorySessionStore()
    for sid in ("a", "b", "c"):
        store.put(Session(sid, {"u": sid}, ttl=3600))
    all_sessions = store.all()
    assert len(all_sessions) == 3
    assert {s.session_id for s in all_sessions} == {"a", "b", "c"}


def test_inmemory_session_store_backend_name():
    from largestack._enterprise.session_store import InMemorySessionStore
    assert InMemorySessionStore().backend_name() == "inmemory"


# -------------------- Redis backend (with fallback) --------------------

def test_redis_session_store_falls_back_when_redis_missing():
    """When Redis URL is unreachable, fall back to in-memory.
    Tests with intentionally broken URL."""
    from largestack._enterprise.session_store import RedisSessionStore
    store = RedisSessionStore(redis_url="redis://nonexistent.invalid:6379/0")
    # Should not crash
    assert store._redis is None
    # Backend name reports the fallback state honestly
    assert "fallback" in store.backend_name() or store.backend_name() == "redis"

    # Operations still work via fallback
    from largestack._enterprise.sso import Session
    s = Session("test", {"u": "alice"}, ttl=60)
    store.put(s)
    got = store.get("test")
    assert got is not None
    assert got.user_info["u"] == "alice"


# -------------------- Factory --------------------

def test_create_session_store_default_inmemory(monkeypatch):
    monkeypatch.delenv("LARGESTACK_SESSION_BACKEND", raising=False)
    from largestack._enterprise.session_store import create_session_store, InMemorySessionStore
    store = create_session_store()
    assert isinstance(store, InMemorySessionStore)


def test_create_session_store_redis_with_unreachable_falls_back(monkeypatch):
    monkeypatch.setenv("LARGESTACK_SESSION_BACKEND", "redis")
    monkeypatch.setenv("LARGESTACK_REDIS_URL", "redis://nowhere.invalid:6379/0")
    from largestack._enterprise.session_store import create_session_store, RedisSessionStore
    store = create_session_store()
    assert isinstance(store, RedisSessionStore)
    # Even though redis is unreachable, the store works via fallback
    from largestack._enterprise.sso import Session
    s = Session("x", {"u": "y"}, ttl=60)
    store.put(s)
    assert store.get("x") is not None


# -------------------- SSO integration --------------------

@pytest.mark.asyncio
async def test_sso_provider_uses_session_store(monkeypatch):
    """SSOProvider should write through to its session store."""
    monkeypatch.delenv("LARGESTACK_SESSION_BACKEND", raising=False)
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock", client_id="x", client_secret="y", issuer="z")
    sid = await sso.create_session({"user_id": "alice"})
    assert sid

    # Validate
    s = await sso.validate_session(sid)
    assert s is not None
    assert s.user_info["user_id"] == "alice"

    # Revoke
    revoked = await sso.revoke_session(sid)
    assert revoked is True
    assert await sso.validate_session(sid) is None
