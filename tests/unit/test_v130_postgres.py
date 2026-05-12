"""v0.13.0: Tests for PostgresLongTermStore.

Uses mocks since asyncpg isn't required at install time. The code
contract is exercised; actual Postgres I/O is verified at integration
time against a real DB.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_postgres_store_module_importable():
    """The Postgres backend module should always be importable."""
    from largestack._memory import postgres_store
    assert hasattr(postgres_store, "PostgresLongTermStore")


def test_postgres_store_raises_without_asyncpg():
    """Constructor must raise ImportError if asyncpg not installed."""
    from largestack._memory.postgres_store import PostgresLongTermStore
    with patch(
        "largestack._memory.postgres_store._have_asyncpg",
        return_value=False,
    ):
        with pytest.raises(ImportError, match="asyncpg"):
            PostgresLongTermStore("postgresql://localhost/test")


def test_postgres_store_dsn_stored():
    from largestack._memory.postgres_store import PostgresLongTermStore
    with patch(
        "largestack._memory.postgres_store._have_asyncpg",
        return_value=True,
    ):
        store = PostgresLongTermStore(
            "postgresql://u:p@h/db",
            pool_min_size=2, pool_max_size=20,
        )
    assert store.dsn == "postgresql://u:p@h/db"
    assert store.pool_min_size == 2
    assert store.pool_max_size == 20
    assert store._pool is None
    assert store._initialized is False


def _mock_store():
    """Construct a store with mocked asyncpg pool."""
    from largestack._memory.postgres_store import PostgresLongTermStore
    with patch(
        "largestack._memory.postgres_store._have_asyncpg",
        return_value=True,
    ):
        store = PostgresLongTermStore("postgresql://test")
    return store


@pytest.mark.asyncio
async def test_postgres_store_add_executes_insert():
    """``add`` should issue a parameterized INSERT."""
    from largestack._memory.long_term import LongTermMemoryEntry
    store = _mock_store()

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="test",
    )
    await store.add(e)
    # Verify INSERT was called
    assert mock_conn.execute.called
    args = mock_conn.execute.call_args[0]
    sql = args[0]
    assert "INSERT INTO lt_memory_entries" in sql
    # Tenant + user + content present in args
    assert "t1" in args
    assert "u1" in args
    assert "test" in args


@pytest.mark.asyncio
async def test_postgres_store_get_returns_none_when_missing():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    result = await store.get("nope")
    assert result is None


@pytest.mark.asyncio
async def test_postgres_store_get_hydrates_entry_from_row():
    store = _mock_store()
    mock_row = {
        "id": "e1", "tenant_id": "t1", "user_id": "u1",
        "tier": "core", "scope": "semantic", "content": "hi",
        "created_at": 1000.0, "last_accessed_at": 1000.0,
        "tag": "x", "source": "y", "purpose": "p",
        "ttl_seconds": None, "lawful_basis": "consent",
        "metadata": "{}",
    }
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    entry = await store.get("e1")
    assert entry is not None
    assert entry.id == "e1"
    assert entry.tenant_id == "t1"
    assert entry.tier == "core"


@pytest.mark.asyncio
async def test_postgres_store_delete_returns_bool():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 1")
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    assert await store.delete("e1") is True

    mock_conn.execute = AsyncMock(return_value="DELETE 0")
    assert await store.delete("nope") is False


@pytest.mark.asyncio
async def test_postgres_store_list_filters_correctly():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    await store.list(tenant_id="t1", user_id="u1", tier="core")
    sql = mock_conn.fetch.call_args[0][0]
    assert "tenant_id = $1" in sql
    assert "user_id = $2" in sql
    assert "tier = $3" in sql


@pytest.mark.asyncio
async def test_postgres_store_search_uses_ilike():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    await store.search(
        tenant_id="t1", user_id="u1", query="aadhaar",
    )
    sql = mock_conn.fetch.call_args[0][0]
    assert "ILIKE" in sql
    # Tenant always parameterized
    assert "tenant_id = $1" in sql


@pytest.mark.asyncio
async def test_postgres_store_purge_returns_count():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 5")
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    count = await store.purge_expired(tenant_id="t1")
    assert count == 5


@pytest.mark.asyncio
async def test_postgres_store_clear_with_tenant_filter():
    store = _mock_store()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 3")
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(
        return_value=_AsyncContextManager(mock_conn),
    )
    store._pool = mock_pool
    store._initialized = True

    count = await store.clear(tenant_id="t1")
    assert count == 3
    sql = mock_conn.execute.call_args[0][0]
    assert "WHERE tenant_id = $1" in sql


@pytest.mark.asyncio
async def test_postgres_store_close_releases_pool():
    store = _mock_store()
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()
    store._pool = mock_pool
    store._initialized = True

    await store.close()
    mock_pool.close.assert_awaited_once()
    assert store._pool is None
    assert store._initialized is False


def test_row_to_entry_handles_dict_metadata():
    """When metadata comes back as already-parsed dict (asyncpg JSONB)."""
    from largestack._memory.postgres_store import PostgresLongTermStore
    row = {
        "id": "e1", "tenant_id": "t1", "user_id": "u1",
        "tier": "core", "scope": "semantic", "content": "x",
        "created_at": 1.0, "last_accessed_at": 1.0,
        "tag": "", "source": "", "purpose": "",
        "ttl_seconds": None, "lawful_basis": "",
        "metadata": {"key": "value"},  # already dict
    }
    entry = PostgresLongTermStore._row_to_entry(row)
    assert entry.metadata == {"key": "value"}


# -------------------- Helper class --------------------

class _AsyncContextManager:
    """Mock for ``async with pool.acquire() as conn:``."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        return None
