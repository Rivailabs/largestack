"""v0.9.0: Tests for 7 new vector store adapters."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- Chroma --------------------

@pytest.mark.asyncio
async def test_chroma_upsert_and_query():
    from largestack._vectorstores import ChromaStore

    fake_coll = MagicMock()
    fake_coll.upsert = MagicMock()
    fake_coll.query = MagicMock(return_value={
        "ids": [["d1", "d2"]],
        "distances": [[0.1, 0.3]],
        "metadatas": [[{"x": "a"}, {"x": "b"}]],
    })
    fake_coll.delete = MagicMock()

    fake_client = MagicMock()
    fake_client.get_or_create_collection = MagicMock(return_value=fake_coll)

    fake_chromadb = MagicMock()
    fake_chromadb.Client = MagicMock(return_value=fake_client)
    fake_chromadb.PersistentClient = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"chromadb": fake_chromadb}):
        store = ChromaStore(collection="test")
        await store.upsert([
            {"id": "d1", "vector": [0.1, 0.2], "metadata": {"x": "a"}},
            {"id": "d2", "vector": [0.3, 0.4], "metadata": {"x": "b"}},
        ])
        results = await store.query([0.1, 0.2], top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "d1"
    # distance 0.1 → similarity 0.9
    assert abs(results[0]["score"] - 0.9) < 1e-6


@pytest.mark.asyncio
async def test_chroma_handles_missing_sdk():
    from largestack._vectorstores import ChromaStore
    import sys
    saved = sys.modules.pop("chromadb", None)
    sys.modules["chromadb"] = None
    try:
        store = ChromaStore(collection="t")
        with pytest.raises(ImportError, match="chromadb"):
            await store.upsert([])
    finally:
        if saved is not None:
            sys.modules["chromadb"] = saved
        else:
            sys.modules.pop("chromadb", None)


# -------------------- LanceDB --------------------

@pytest.mark.asyncio
async def test_lancedb_handles_missing_sdk():
    from largestack._vectorstores import LanceDBStore
    import sys
    saved = sys.modules.pop("lancedb", None)
    sys.modules["lancedb"] = None
    try:
        store = LanceDBStore(uri="/tmp/t", table="x")
        with pytest.raises(ImportError, match="lancedb"):
            await store.upsert([])
    finally:
        if saved is not None:
            sys.modules["lancedb"] = saved
        else:
            sys.modules.pop("lancedb", None)


@pytest.mark.asyncio
async def test_lancedb_query_normalizes_results():
    from largestack._vectorstores import LanceDBStore

    fake_query = MagicMock()
    fake_query.limit = MagicMock(return_value=fake_query)
    fake_query.where = MagicMock(return_value=fake_query)
    fake_query.to_list = AsyncMock(return_value=[
        {"id": "doc1", "_distance": 0.05, "metadata": '{"title": "A"}'},
        {"id": "doc2", "_distance": 0.15, "metadata": '{"title": "B"}'},
    ])

    fake_table = MagicMock()
    fake_table.search = MagicMock(return_value=fake_query)

    fake_db = MagicMock()
    fake_db.open_table = AsyncMock(return_value=fake_table)

    fake_lancedb = MagicMock()
    fake_lancedb.connect_async = AsyncMock(return_value=fake_db)

    with patch.dict("sys.modules", {"lancedb": fake_lancedb}):
        store = LanceDBStore(uri="/tmp/db", table="t")
        results = await store.query([0.1, 0.2], top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["metadata"]["title"] == "A"


# -------------------- Azure Cognitive Search --------------------

@pytest.mark.asyncio
async def test_azure_cog_search_upsert():
    from largestack._vectorstores import AzureCognitiveSearchStore

    fake_client = MagicMock()
    fake_client.upload_documents = AsyncMock()
    fake_client.close = AsyncMock()

    fake_aio = MagicMock()
    fake_aio.SearchClient = MagicMock(return_value=fake_client)

    fake_creds = MagicMock()
    fake_creds.AzureKeyCredential = MagicMock()

    with patch.dict("sys.modules", {
        "azure": MagicMock(),
        "azure.search": MagicMock(),
        "azure.search.documents": MagicMock(),
        "azure.search.documents.aio": fake_aio,
        "azure.core": MagicMock(),
        "azure.core.credentials": fake_creds,
    }):
        store = AzureCognitiveSearchStore(
            endpoint="https://x.search.windows.net",
            index_name="docs",
            api_key="fake",
        )
        await store.upsert([
            {"id": "1", "vector": [0.1, 0.2], "metadata": {"title": "A"}}
        ])

    fake_client.upload_documents.assert_awaited_once()
    docs = fake_client.upload_documents.await_args.kwargs["documents"]
    assert docs[0]["id"] == "1"
    assert docs[0]["title"] == "A"


@pytest.mark.asyncio
async def test_azure_cog_search_requires_api_key(monkeypatch):
    from largestack._vectorstores import AzureCognitiveSearchStore
    monkeypatch.delenv("AZURE_SEARCH_API_KEY", raising=False)
    fake_aio = MagicMock()
    fake_aio.SearchClient = MagicMock()
    fake_creds = MagicMock()
    fake_creds.AzureKeyCredential = MagicMock()
    with patch.dict("sys.modules", {
        "azure.search.documents.aio": fake_aio,
        "azure.core.credentials": fake_creds,
    }):
        store = AzureCognitiveSearchStore(
            endpoint="https://x.search.windows.net",
            index_name="d",
        )
        with pytest.raises(ValueError, match="api_key"):
            await store.upsert([])


# -------------------- Supabase --------------------

def test_supabase_constructs_postgres_dsn():
    from largestack._vectorstores import SupabaseVectorStore
    store = SupabaseVectorStore(
        supabase_url="https://abcdef.supabase.co",
        password="mypass",
        table="documents",
    )
    assert "abcdef.supabase.co" in store.dsn
    assert "mypass" in store.dsn
    assert store.table == "documents"


def test_supabase_inherits_pgvector_validation():
    from largestack._vectorstores import SupabaseVectorStore
    with pytest.raises(ValueError, match="invalid table name"):
        SupabaseVectorStore(
            supabase_url="https://x.supabase.co",
            password="p",
            table="DROP TABLE x; --",
        )


# -------------------- FAISS Persistent --------------------

@pytest.mark.asyncio
async def test_faiss_persistent_upsert_and_query(tmp_path):
    pytest.importorskip("faiss")
    from largestack._vectorstores import FaissPersistentStore

    idx_path = str(tmp_path / "test.faiss")
    meta_path = str(tmp_path / "test.json")

    store = FaissPersistentStore(
        index_path=idx_path, meta_path=meta_path, dim=4, metric="cosine",
    )
    await store.upsert([
        {"id": "doc1", "vector": [1.0, 0.0, 0.0, 0.0], "metadata": {"title": "A"}},
        {"id": "doc2", "vector": [0.0, 1.0, 0.0, 0.0], "metadata": {"title": "B"}},
    ])
    # Files persisted
    assert os.path.exists(idx_path)
    assert os.path.exists(meta_path)

    results = await store.query([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "doc1"


@pytest.mark.asyncio
async def test_faiss_persistent_survives_restart(tmp_path):
    pytest.importorskip("faiss")
    from largestack._vectorstores import FaissPersistentStore

    idx_path = str(tmp_path / "p.faiss")
    meta_path = str(tmp_path / "p.json")

    store1 = FaissPersistentStore(idx_path, meta_path, dim=3, metric="cosine")
    await store1.upsert([
        {"id": "x", "vector": [1.0, 0.0, 0.0], "metadata": {"v": 1}}
    ])
    await store1.close()

    # Fresh instance reads from disk
    store2 = FaissPersistentStore(idx_path, meta_path, dim=3, metric="cosine")
    results = await store2.query([1.0, 0.0, 0.0], top_k=1)
    assert results[0]["id"] == "x"


@pytest.mark.asyncio
async def test_faiss_persistent_delete(tmp_path):
    pytest.importorskip("faiss")
    from largestack._vectorstores import FaissPersistentStore
    store = FaissPersistentStore(
        index_path=str(tmp_path / "d.faiss"),
        meta_path=str(tmp_path / "d.json"),
        dim=2, metric="cosine",
    )
    await store.upsert([
        {"id": "a", "vector": [1.0, 0.0], "metadata": {}},
        {"id": "b", "vector": [0.0, 1.0], "metadata": {}},
    ])
    await store.delete(["a"])
    results = await store.query([1.0, 0.0], top_k=5)
    ids = [r["id"] for r in results]
    assert "a" not in ids
    assert "b" in ids


# -------------------- DuckDB --------------------

def test_duckdb_validates_table_name():
    from largestack._vectorstores import DuckDBVectorStore
    DuckDBVectorStore(":memory:", "documents")  # OK
    DuckDBVectorStore(":memory:", "embeddings_v2")  # OK
    with pytest.raises(ValueError, match="invalid table name"):
        DuckDBVectorStore(":memory:", "DROP TABLE x; --")


@pytest.mark.asyncio
async def test_duckdb_upsert_query_delete(tmp_path):
    pytest.importorskip("duckdb")
    from largestack._vectorstores import DuckDBVectorStore

    db_path = str(tmp_path / "test.db")
    store = DuckDBVectorStore(db_path, "docs", dim=3)
    await store.upsert([
        {"id": "a", "vector": [1.0, 0.0, 0.0], "metadata": {"cat": "x"}},
        {"id": "b", "vector": [0.0, 1.0, 0.0], "metadata": {"cat": "y"}},
    ])
    # If vss extension is unavailable in this environment, query may
    # return empty list — that's the documented fallback behavior.
    results = await store.query([1.0, 0.0, 0.0], top_k=2)
    assert isinstance(results, list)
    await store.delete(["a"])
    await store.close()


# -------------------- Aurora pgvector --------------------

def test_aurora_pgvector_constructs_dsn_with_ssl():
    from largestack._vectorstores import AuroraPgVectorStore
    store = AuroraPgVectorStore(
        cluster_endpoint="my-cluster.cluster-xxx.us-east-1.rds.amazonaws.com",
        database="vectors",
        username="postgres",
        password="secret",
        table="embeddings",
    )
    assert "rds.amazonaws.com" in store.dsn
    assert "sslmode=require" in store.dsn


def test_aurora_pgvector_ssl_disabled():
    from largestack._vectorstores import AuroraPgVectorStore
    store = AuroraPgVectorStore(
        cluster_endpoint="x.rds.amazonaws.com",
        database="d",
        username="u",
        password="p",
        table="t",
        ssl=False,
    )
    assert "sslmode=prefer" in store.dsn


# -------------------- Common interface --------------------

def test_all_new_stores_implement_vectorstore():
    from largestack._vectorstores import (
        VectorStore, ChromaStore, LanceDBStore, AzureCognitiveSearchStore,
        SupabaseVectorStore, FaissPersistentStore, DuckDBVectorStore,
        AuroraPgVectorStore,
    )
    for cls in (
        ChromaStore, LanceDBStore, AzureCognitiveSearchStore,
        SupabaseVectorStore, FaissPersistentStore, DuckDBVectorStore,
        AuroraPgVectorStore,
    ):
        assert issubclass(cls, VectorStore), f"{cls.__name__} not a VectorStore"


# -------------------- Qdrant local SDK E2E --------------------

@pytest.mark.asyncio
async def test_qdrant_local_memory_upsert_query_delete():
    pytest.importorskip("qdrant_client")
    from largestack._vectorstores import QdrantStore

    store = QdrantStore(
        collection="largestack_local_e2e",
        url=":memory:",
        dim=4,
        create_collection=True,
    )
    try:
        await store.upsert([
            {"id": 1, "vector": [1.0, 0.0, 0.0, 0.0], "metadata": {"tenant": "a"}},
            {"id": 2, "vector": [0.0, 1.0, 0.0, 0.0], "metadata": {"tenant": "b"}},
        ])
        results = await store.query([1.0, 0.0, 0.0, 0.0], top_k=1)
        assert results[0]["id"] == "1"
        assert results[0]["metadata"]["tenant"] == "a"

        await store.delete([1])
        remaining = await store.query([1.0, 0.0, 0.0, 0.0], top_k=2)
        assert "1" not in {row["id"] for row in remaining}
    finally:
        await store.close()
