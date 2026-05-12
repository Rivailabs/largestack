"""v0.10.0: Tests for MongoAtlas + Elasticsearch dense vector stores."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- MongoAtlas Vector --------------------

@pytest.mark.asyncio
async def test_mongo_atlas_handles_missing_motor():
    from largestack._vectorstores import MongoAtlasVectorStore
    import sys
    saved = sys.modules.pop("motor", None)
    saved_async = sys.modules.pop("motor.motor_asyncio", None)
    sys.modules["motor"] = None
    sys.modules["motor.motor_asyncio"] = None
    try:
        store = MongoAtlasVectorStore(
            uri="mongodb+srv://x", database="d", collection="c",
        )
        with pytest.raises(ImportError, match="motor"):
            await store.upsert([])
    finally:
        if saved is not None:
            sys.modules["motor"] = saved
        else:
            sys.modules.pop("motor", None)
        if saved_async is not None:
            sys.modules["motor.motor_asyncio"] = saved_async
        else:
            sys.modules.pop("motor.motor_asyncio", None)


@pytest.mark.asyncio
async def test_mongo_atlas_query_uses_vectorsearch_aggregation():
    """Verify $vectorSearch stage is used."""
    from largestack._vectorstores import MongoAtlasVectorStore

    # Build mock cursor that yields docs
    class _AsyncIter:
        def __init__(self, items):
            self._items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    fake_coll = MagicMock()
    fake_coll.aggregate = MagicMock(return_value=_AsyncIter([
        {"_id": "doc1", "metadata": {"k": "v"}, "score": 0.95},
        {"_id": "doc2", "metadata": {"k": "w"}, "score": 0.80},
    ]))

    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(return_value=fake_coll)
    fake_client = MagicMock()
    fake_client.__getitem__ = MagicMock(return_value=fake_db)

    fake_motor_async = MagicMock()
    fake_motor_async.AsyncIOMotorClient = MagicMock(return_value=fake_client)
    fake_motor = MagicMock()
    fake_motor.motor_asyncio = fake_motor_async

    with patch.dict("sys.modules", {
        "motor": fake_motor, "motor.motor_asyncio": fake_motor_async,
    }):
        store = MongoAtlasVectorStore(
            uri="mongodb+srv://x", database="d", collection="c",
            index_name="my_index",
        )
        results = await store.query([0.1, 0.2, 0.3], top_k=2)

    # Verify we got both docs back
    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] == 0.95

    # Verify aggregation used $vectorSearch
    call_args = fake_coll.aggregate.call_args
    pipeline = call_args.args[0] if call_args.args else call_args.kwargs.get("pipeline")
    assert pipeline is not None
    assert "$vectorSearch" in pipeline[0]
    assert pipeline[0]["$vectorSearch"]["index"] == "my_index"


@pytest.mark.asyncio
async def test_mongo_atlas_query_with_filter():
    from largestack._vectorstores import MongoAtlasVectorStore

    class _AsyncIter:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise StopAsyncIteration

    fake_coll = MagicMock()
    fake_coll.aggregate = MagicMock(return_value=_AsyncIter())
    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(return_value=fake_coll)
    fake_client = MagicMock()
    fake_client.__getitem__ = MagicMock(return_value=fake_db)

    fake_motor_async = MagicMock()
    fake_motor_async.AsyncIOMotorClient = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {
        "motor": MagicMock(motor_asyncio=fake_motor_async),
        "motor.motor_asyncio": fake_motor_async,
    }):
        store = MongoAtlasVectorStore(
            uri="mongodb+srv://x", database="d", collection="c",
        )
        await store.query([0.1, 0.2], top_k=5, filter={"category": "blog"})

    pipeline = fake_coll.aggregate.call_args.args[0]
    # Verify filter was converted to metadata.* prefix
    assert pipeline[0]["$vectorSearch"]["filter"] == {"metadata.category": "blog"}


# -------------------- Elasticsearch dense_vector --------------------

@pytest.mark.asyncio
async def test_es_dense_handles_missing_sdk():
    from largestack._vectorstores import ElasticsearchDenseVectorStore
    import sys
    saved = sys.modules.pop("elasticsearch", None)
    sys.modules["elasticsearch"] = None
    try:
        store = ElasticsearchDenseVectorStore(
            hosts=["http://localhost:9200"], index="docs",
        )
        with pytest.raises(ImportError, match="elasticsearch"):
            await store.upsert([])
    finally:
        if saved is not None:
            sys.modules["elasticsearch"] = saved
        else:
            sys.modules.pop("elasticsearch", None)


@pytest.mark.asyncio
async def test_es_dense_upsert_uses_bulk():
    from largestack._vectorstores import ElasticsearchDenseVectorStore

    fake_client = MagicMock()
    fake_client.bulk = AsyncMock()

    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchDenseVectorStore(
            hosts=["http://localhost:9200"], index="docs",
            api_key="elastic_key",
        )
        await store.upsert([
            {"id": "1", "vector": [0.1, 0.2], "metadata": {"x": "a"}},
            {"id": "2", "vector": [0.3, 0.4], "metadata": {"x": "b"}},
        ])

    fake_client.bulk.assert_awaited_once()
    # Verify bulk operations format: alternating index meta + doc
    ops = fake_client.bulk.call_args.kwargs["operations"]
    assert len(ops) == 4  # 2 docs × 2 ops
    assert "index" in ops[0]
    assert ops[0]["index"]["_id"] == "1"
    assert "embedding" in ops[1]


@pytest.mark.asyncio
async def test_es_dense_query_with_filter():
    from largestack._vectorstores import ElasticsearchDenseVectorStore

    fake_client = MagicMock()
    fake_client.search = AsyncMock(return_value={
        "hits": {"hits": [
            {"_id": "doc1", "_score": 0.92,
             "_source": {"metadata": {"title": "First"}}},
            {"_id": "doc2", "_score": 0.85,
             "_source": {"metadata": {"title": "Second"}}},
        ]}
    })

    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchDenseVectorStore(
            hosts=["http://localhost:9200"], index="docs",
        )
        results = await store.query(
            [0.1, 0.2, 0.3], top_k=2,
            filter={"category": "rust", "year": 2024},
        )

    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] == 0.92

    # Verify knn clause structure
    call_kw = fake_client.search.call_args.kwargs
    assert call_kw["index"] == "docs"
    knn = call_kw["knn"]
    assert knn["field"] == "embedding"
    assert "filter" in knn  # filter applied


@pytest.mark.asyncio
async def test_es_dense_delete():
    from largestack._vectorstores import ElasticsearchDenseVectorStore

    fake_client = MagicMock()
    fake_client.delete = AsyncMock()

    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchDenseVectorStore(
            hosts=["http://localhost:9200"], index="docs",
        )
        await store.delete(["doc1", "doc2"])

    assert fake_client.delete.await_count == 2


def test_mongo_atlas_implements_vectorstore():
    from largestack._vectorstores import VectorStore, MongoAtlasVectorStore
    assert issubclass(MongoAtlasVectorStore, VectorStore)


def test_es_dense_implements_vectorstore():
    from largestack._vectorstores import VectorStore, ElasticsearchDenseVectorStore
    assert issubclass(ElasticsearchDenseVectorStore, VectorStore)


def test_es_dense_accepts_string_or_list_hosts():
    from largestack._vectorstores import ElasticsearchDenseVectorStore
    s1 = ElasticsearchDenseVectorStore(
        hosts="http://localhost:9200", index="docs",
    )
    assert isinstance(s1.hosts, list)
    s2 = ElasticsearchDenseVectorStore(
        hosts=["http://a:9200", "http://b:9200"], index="docs",
    )
    assert len(s2.hosts) == 2
