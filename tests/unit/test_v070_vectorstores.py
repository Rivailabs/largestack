"""v0.7.0: Vector store adapter tests.

Mocks each underlying SDK so tests don't need real Pinecone/Weaviate/
Postgres instances. Verifies the adapter layer behavior — that calls
flow through to the right SDK methods with the right args.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- Pinecone --------------------

@pytest.mark.asyncio
async def test_pinecone_upsert_calls_async_client():
    from largestack._vectorstores import PineconeStore

    fake_idx = MagicMock()
    fake_idx.upsert = AsyncMock()
    fake_idx.close = AsyncMock()
    fake_pc = MagicMock()
    fake_pc.IndexAsyncio = MagicMock(return_value=fake_idx)
    fake_pc.close = AsyncMock()

    fake_pinecone_mod = MagicMock()
    fake_pinecone_mod.PineconeAsyncio = MagicMock(return_value=fake_pc)

    with patch.dict("sys.modules", {"pinecone": fake_pinecone_mod}):
        store = PineconeStore(
            index_name="test", api_key="fake", host="test.pinecone.io"
        )
        await store.upsert([
            {"id": "1", "vector": [0.1, 0.2], "metadata": {"x": "a"}},
            {"id": "2", "vector": [0.3, 0.4], "metadata": {"x": "b"}},
        ])
        await store.close()

    fake_idx.upsert.assert_awaited_once()
    args, kwargs = fake_idx.upsert.call_args
    vectors_arg = kwargs.get("vectors") or (args[0] if args else None)
    assert len(vectors_arg) == 2
    assert vectors_arg[0]["id"] == "1"
    assert vectors_arg[0]["values"] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_pinecone_query_returns_normalized_results():
    from largestack._vectorstores import PineconeStore

    match1 = MagicMock()
    match1.id = "doc1"
    match1.score = 0.95
    match1.metadata = {"title": "first"}
    match2 = MagicMock()
    match2.id = "doc2"
    match2.score = 0.80
    match2.metadata = {"title": "second"}

    fake_resp = MagicMock()
    fake_resp.matches = [match1, match2]

    fake_idx = MagicMock()
    fake_idx.query = AsyncMock(return_value=fake_resp)
    fake_idx.close = AsyncMock()
    fake_pc = MagicMock()
    fake_pc.IndexAsyncio = MagicMock(return_value=fake_idx)
    fake_pc.close = AsyncMock()

    fake_pinecone_mod = MagicMock()
    fake_pinecone_mod.PineconeAsyncio = MagicMock(return_value=fake_pc)

    with patch.dict("sys.modules", {"pinecone": fake_pinecone_mod}):
        store = PineconeStore(index_name="test", api_key="fake", host="x.pinecone.io")
        results = await store.query([0.1, 0.2], top_k=5)

    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] == 0.95
    assert results[0]["metadata"]["title"] == "first"


@pytest.mark.asyncio
async def test_pinecone_requires_api_key():
    from largestack._vectorstores import PineconeStore
    import os
    saved = os.environ.pop("PINECONE_API_KEY", None)
    try:
        store = PineconeStore(index_name="t")
        fake_pinecone_mod = MagicMock()
        fake_pinecone_mod.PineconeAsyncio = MagicMock()
        with patch.dict("sys.modules", {"pinecone": fake_pinecone_mod}):
            with pytest.raises(ValueError, match="api_key"):
                await store.upsert([])
    finally:
        if saved:
            os.environ["PINECONE_API_KEY"] = saved


@pytest.mark.asyncio
async def test_pinecone_raises_clear_error_when_sdk_missing():
    """Without pinecone installed, raise informative ImportError."""
    from largestack._vectorstores import PineconeStore
    store = PineconeStore(index_name="t", api_key="fake", host="x.pinecone.io")

    # Mock the import to fail
    import sys
    original_pinecone = sys.modules.pop("pinecone", None)
    sys.modules["pinecone"] = None  # forces ImportError on `from pinecone import ...`
    try:
        with pytest.raises(ImportError, match="pinecone"):
            await store.upsert([])
    finally:
        if original_pinecone is not None:
            sys.modules["pinecone"] = original_pinecone
        else:
            sys.modules.pop("pinecone", None)


# -------------------- Weaviate --------------------

@pytest.mark.asyncio
async def test_weaviate_upsert_calls_data_insert():
    from largestack._vectorstores import WeaviateStore

    fake_collection = MagicMock()
    fake_collection.data.insert = AsyncMock()
    fake_collection.data.delete_by_id = AsyncMock()

    fake_client = MagicMock()
    fake_client.connect = AsyncMock()
    fake_client.close = AsyncMock()
    fake_client.collections.use = MagicMock(return_value=fake_collection)

    fake_weaviate = MagicMock()
    fake_weaviate.use_async_with_local = MagicMock(return_value=fake_client)
    fake_weaviate.classes.init.Auth = MagicMock()

    with patch.dict("sys.modules", {
        "weaviate": fake_weaviate,
        "weaviate.classes.init": fake_weaviate.classes.init,
        "weaviate.classes.query": MagicMock(),
    }):
        store = WeaviateStore(collection="MyClass")
        await store.upsert([
            {"id": "abc", "vector": [0.1, 0.2], "metadata": {"name": "test"}},
        ])

    fake_collection.data.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_weaviate_close_releases_client():
    from largestack._vectorstores import WeaviateStore

    fake_collection = MagicMock()
    fake_client = MagicMock()
    fake_client.connect = AsyncMock()
    fake_client.close = AsyncMock()
    fake_client.collections.use = MagicMock(return_value=fake_collection)

    fake_weaviate = MagicMock()
    fake_weaviate.use_async_with_local = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {
        "weaviate": fake_weaviate,
        "weaviate.classes.init": fake_weaviate.classes.init,
        "weaviate.classes.query": MagicMock(),
    }):
        store = WeaviateStore(collection="X")
        # Trigger connect via upsert (no-op)
        fake_collection.data.insert = AsyncMock()
        await store.upsert([])
        await store.close()

    fake_client.close.assert_awaited_once()


# -------------------- pgvector --------------------

def test_pgvector_table_validation():
    """Table name must be a safe SQL identifier."""
    from largestack._vectorstores import PgVectorStore
    PgVectorStore("postgres://x", "documents")  # OK
    PgVectorStore("postgres://x", "embeddings_v2")  # OK
    with pytest.raises(ValueError, match="invalid table name"):
        PgVectorStore("postgres://x", "drop table users; --")
    with pytest.raises(ValueError, match="invalid table name"):
        PgVectorStore("postgres://x", "")
    with pytest.raises(ValueError, match="invalid table name"):
        PgVectorStore("postgres://x", "1starts_with_digit")


@pytest.mark.asyncio
async def test_pgvector_upsert_executes_correct_sql():
    from largestack._vectorstores import PgVectorStore

    fake_conn = MagicMock()
    fake_conn.execute = AsyncMock()
    fake_pool = MagicMock()
    
    class _AcquireCtx:
        async def __aenter__(self): return fake_conn
        async def __aexit__(self, *a): return None
    fake_pool.acquire = MagicMock(return_value=_AcquireCtx())
    fake_pool.close = AsyncMock()

    fake_asyncpg = MagicMock()
    fake_asyncpg.create_pool = AsyncMock(return_value=fake_pool)

    with patch.dict("sys.modules", {"asyncpg": fake_asyncpg}):
        store = PgVectorStore("postgres://test", "documents")
        await store.upsert([
            {"id": "doc1", "vector": [0.1, 0.2, 0.3], "metadata": {"title": "x"}},
        ])

    fake_conn.execute.assert_awaited()
    args = fake_conn.execute.await_args.args
    sql = args[0]
    assert "INSERT INTO documents" in sql
    assert "ON CONFLICT" in sql
    assert args[1] == "doc1"
    assert args[2] == "[0.1,0.2,0.3]"


@pytest.mark.asyncio
async def test_pgvector_query_orders_by_distance():
    from largestack._vectorstores import PgVectorStore

    fake_rows = [
        {"id": "doc1", "score": 0.95, "metadata": '{"title": "first"}'},
        {"id": "doc2", "score": 0.80, "metadata": '{"title": "second"}'},
    ]
    fake_conn = MagicMock()
    fake_conn.fetch = AsyncMock(return_value=fake_rows)
    fake_pool = MagicMock()
    
    class _AcquireCtx:
        async def __aenter__(self): return fake_conn
        async def __aexit__(self, *a): return None
    fake_pool.acquire = MagicMock(return_value=_AcquireCtx())
    fake_pool.close = AsyncMock()

    fake_asyncpg = MagicMock()
    fake_asyncpg.create_pool = AsyncMock(return_value=fake_pool)

    with patch.dict("sys.modules", {"asyncpg": fake_asyncpg}):
        store = PgVectorStore("postgres://test", "documents")
        results = await store.query([0.1, 0.2, 0.3], top_k=5)

    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] == 0.95
    assert results[0]["metadata"]["title"] == "first"

    sql = fake_conn.fetch.await_args.args[0]
    assert "ORDER BY embedding <=>" in sql
    assert "LIMIT $2" in sql


@pytest.mark.asyncio
async def test_pgvector_query_with_metadata_filter():
    from largestack._vectorstores import PgVectorStore

    fake_conn = MagicMock()
    fake_conn.fetch = AsyncMock(return_value=[])
    fake_pool = MagicMock()
    
    class _AcquireCtx:
        async def __aenter__(self): return fake_conn
        async def __aexit__(self, *a): return None
    fake_pool.acquire = MagicMock(return_value=_AcquireCtx())
    fake_pool.close = AsyncMock()

    fake_asyncpg = MagicMock()
    fake_asyncpg.create_pool = AsyncMock(return_value=fake_pool)

    with patch.dict("sys.modules", {"asyncpg": fake_asyncpg}):
        store = PgVectorStore("postgres://test", "documents")
        await store.query([0.1, 0.2], top_k=10, filter={"category": "tech"})

    sql = fake_conn.fetch.await_args.args[0]
    assert "WHERE" in sql
    assert "metadata->>$2" in sql


# -------------------- Common interface --------------------

def test_all_three_implement_vectorstore():
    from largestack._vectorstores import VectorStore, PineconeStore, WeaviateStore, PgVectorStore
    assert issubclass(PineconeStore, VectorStore)
    assert issubclass(WeaviateStore, VectorStore)
    assert issubclass(PgVectorStore, VectorStore)
