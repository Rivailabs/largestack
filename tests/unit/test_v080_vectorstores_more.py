"""v0.8.0: Tests for 5 new vector store adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- Milvus --------------------


@pytest.mark.asyncio
async def test_milvus_upsert_calls_async_client():
    from largestack._vectorstores import MilvusStore

    fake_client = MagicMock()
    fake_client.upsert = AsyncMock()
    fake_client.close = AsyncMock()

    fake_pymilvus = MagicMock()
    fake_pymilvus.AsyncMilvusClient = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"pymilvus": fake_pymilvus}):
        store = MilvusStore(collection="docs", uri="http://localhost:19530", token="t")
        await store.upsert(
            [
                {"id": "1", "vector": [0.1, 0.2], "metadata": {"x": "a"}},
            ]
        )

    fake_client.upsert.assert_awaited_once()
    args = fake_client.upsert.await_args.kwargs
    assert args["collection_name"] == "docs"
    assert args["data"][0]["id"] == "1"


@pytest.mark.asyncio
async def test_milvus_query_normalizes_results():
    from largestack._vectorstores import MilvusStore

    fake_client = MagicMock()
    fake_client.search = AsyncMock(
        return_value=[
            [
                {"id": "doc1", "distance": 0.92, "entity": {"metadata": {"title": "A"}}},
                {"id": "doc2", "distance": 0.78, "entity": {"metadata": {"title": "B"}}},
            ]
        ]
    )
    fake_pymilvus = MagicMock()
    fake_pymilvus.AsyncMilvusClient = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"pymilvus": fake_pymilvus}):
        store = MilvusStore(collection="docs")
        results = await store.query([0.1, 0.2], top_k=3)

    assert len(results) == 2
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] == 0.92
    assert results[0]["metadata"]["title"] == "A"


@pytest.mark.asyncio
async def test_milvus_delete():
    from largestack._vectorstores import MilvusStore

    fake_client = MagicMock()
    fake_client.delete = AsyncMock()
    fake_pymilvus = MagicMock()
    fake_pymilvus.AsyncMilvusClient = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"pymilvus": fake_pymilvus}):
        store = MilvusStore(collection="d")
        await store.delete(["1", "2"])
    fake_client.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_milvus_raises_when_sdk_missing():
    from largestack._vectorstores import MilvusStore
    import sys

    saved = sys.modules.pop("pymilvus", None)
    sys.modules["pymilvus"] = None  # force ImportError on `from pymilvus import ...`
    try:
        store = MilvusStore(collection="d")
        with pytest.raises(ImportError, match="pymilvus"):
            await store.upsert([])
    finally:
        if saved is not None:
            sys.modules["pymilvus"] = saved
        else:
            sys.modules.pop("pymilvus", None)


# -------------------- Redis Vector --------------------


@pytest.mark.asyncio
async def test_redis_vector_upsert_writes_hashes():
    from largestack._vectorstores import RedisVectorStore

    fake_client = MagicMock()
    fake_client.hset = AsyncMock()
    fake_client.aclose = AsyncMock()

    fake_redis_async_mod = MagicMock()
    fake_redis_async_mod.from_url = MagicMock(return_value=fake_client)
    fake_redis_pkg = MagicMock()
    fake_redis_pkg.asyncio = fake_redis_async_mod

    with patch.dict(
        "sys.modules",
        {
            "redis": fake_redis_pkg,
            "redis.asyncio": fake_redis_async_mod,
        },
    ):
        store = RedisVectorStore(url="redis://localhost", index_name="idx")
        await store.upsert(
            [
                {"id": "doc1", "vector": [0.1, 0.2, 0.3], "metadata": {"title": "Test"}},
            ]
        )

    fake_client.hset.assert_awaited_once()
    call = fake_client.hset.await_args
    assert call.args[0] == "doc:doc1"
    mapping = call.kwargs["mapping"]
    assert "embedding" in mapping
    assert mapping["title"] == "Test"


@pytest.mark.asyncio
async def test_redis_vector_query_parses_ft_search_response():
    from largestack._vectorstores import RedisVectorStore

    fake_client = MagicMock()
    # FT.SEARCH response: [count, key1, [field1, val1, ...]]
    fake_client.execute_command = AsyncMock(
        return_value=[
            2,
            b"doc:abc",
            [b"score", b"0.95", b"title", b"First"],
            b"doc:xyz",
            [b"score", b"0.80", b"title", b"Second"],
        ]
    )
    fake_client.aclose = AsyncMock()

    fake_redis_async_mod = MagicMock()
    fake_redis_async_mod.from_url = MagicMock(return_value=fake_client)
    fake_redis_pkg = MagicMock()
    fake_redis_pkg.asyncio = fake_redis_async_mod

    with patch.dict(
        "sys.modules",
        {
            "redis": fake_redis_pkg,
            "redis.asyncio": fake_redis_async_mod,
        },
    ):
        store = RedisVectorStore(url="redis://localhost", index_name="idx")
        results = await store.query([0.1, 0.2, 0.3], top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "abc"
    assert results[0]["score"] == 0.95
    assert results[0]["metadata"]["title"] == "First"


@pytest.mark.asyncio
async def test_redis_vector_delete_removes_keys():
    from largestack._vectorstores import RedisVectorStore

    fake_client = MagicMock()
    fake_client.delete = AsyncMock()
    fake_client.aclose = AsyncMock()
    fake_redis_async_mod = MagicMock()
    fake_redis_async_mod.from_url = MagicMock(return_value=fake_client)
    fake_redis_pkg = MagicMock()
    fake_redis_pkg.asyncio = fake_redis_async_mod

    with patch.dict(
        "sys.modules",
        {
            "redis": fake_redis_pkg,
            "redis.asyncio": fake_redis_async_mod,
        },
    ):
        store = RedisVectorStore(url="redis://localhost", index_name="idx")
        await store.delete(["a", "b"])
    fake_client.delete.assert_awaited_once_with("doc:a", "doc:b")


# -------------------- Elasticsearch --------------------


@pytest.mark.asyncio
async def test_elasticsearch_upsert_calls_index():
    from largestack._vectorstores import ElasticsearchStore

    fake_client = MagicMock()
    fake_client.index = AsyncMock()
    fake_client.close = AsyncMock()
    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchStore(index="docs", api_key="abc")
        await store.upsert(
            [
                {"id": "1", "vector": [0.1, 0.2], "metadata": {"title": "A"}},
            ]
        )
    fake_client.index.assert_awaited_once()
    kw = fake_client.index.await_args.kwargs
    assert kw["index"] == "docs"
    assert kw["id"] == "1"
    assert kw["document"]["title"] == "A"


@pytest.mark.asyncio
async def test_elasticsearch_query_uses_knn():
    from largestack._vectorstores import ElasticsearchStore

    fake_client = MagicMock()
    fake_client.search = AsyncMock(
        return_value={
            "hits": {
                "hits": [
                    {"_id": "1", "_score": 0.9, "_source": {"title": "A", "embedding": [0.1]}},
                ]
            }
        }
    )
    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchStore(index="docs")
        results = await store.query([0.1, 0.2], top_k=5)

    fake_client.search.assert_awaited_once()
    knn = fake_client.search.await_args.kwargs["knn"]
    assert knn["k"] == 5
    assert results[0]["id"] == "1"
    # embedding field stripped from metadata
    assert "embedding" not in results[0]["metadata"]


@pytest.mark.asyncio
async def test_elasticsearch_query_with_filter():
    from largestack._vectorstores import ElasticsearchStore

    fake_client = MagicMock()
    fake_client.search = AsyncMock(return_value={"hits": {"hits": []}})
    fake_es = MagicMock()
    fake_es.AsyncElasticsearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"elasticsearch": fake_es}):
        store = ElasticsearchStore(index="docs")
        await store.query([0.1, 0.2], top_k=5, filter={"category": "tech"})

    knn = fake_client.search.await_args.kwargs["knn"]
    assert "filter" in knn


# -------------------- OpenSearch --------------------


@pytest.mark.asyncio
async def test_opensearch_upsert_and_query():
    from largestack._vectorstores import OpenSearchStore

    fake_client = MagicMock()
    fake_client.index = AsyncMock()
    fake_client.search = AsyncMock(
        return_value={"hits": {"hits": [{"_id": "x", "_score": 0.8, "_source": {"title": "X"}}]}}
    )
    fake_client.close = AsyncMock()
    fake_os = MagicMock()
    fake_os.AsyncOpenSearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"opensearchpy": fake_os}):
        store = OpenSearchStore(index="d", http_auth=("u", "p"))
        await store.upsert([{"id": "x", "vector": [0.1], "metadata": {"title": "X"}}])
        results = await store.query([0.1], top_k=5)

    assert results[0]["id"] == "x"
    fake_client.index.assert_awaited()


@pytest.mark.asyncio
async def test_opensearch_query_with_filter_uses_bool():
    from largestack._vectorstores import OpenSearchStore

    fake_client = MagicMock()
    fake_client.search = AsyncMock(return_value={"hits": {"hits": []}})
    fake_os = MagicMock()
    fake_os.AsyncOpenSearch = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"opensearchpy": fake_os}):
        store = OpenSearchStore(index="d")
        await store.query([0.1], top_k=5, filter={"tag": "ai"})

    body = fake_client.search.await_args.kwargs["body"]
    assert "bool" in body["query"]


# -------------------- MongoDB Atlas --------------------


@pytest.mark.asyncio
async def test_mongo_atlas_upsert_uses_replace_one():
    from largestack._vectorstores import MongoDBAtlasStore

    fake_coll = MagicMock()
    fake_coll.replace_one = AsyncMock()
    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(return_value=fake_coll)
    fake_client = MagicMock()
    fake_client.__getitem__ = MagicMock(return_value=fake_db)
    fake_client.close = MagicMock()  # motor's close is sync

    fake_motor = MagicMock()
    fake_motor.motor_asyncio.AsyncIOMotorClient = MagicMock(return_value=fake_client)

    with patch.dict(
        "sys.modules",
        {
            "motor": fake_motor,
            "motor.motor_asyncio": fake_motor.motor_asyncio,
        },
    ):
        store = MongoDBAtlasStore(uri="mongodb://test", database="db", collection="docs")
        await store.upsert(
            [
                {"id": "1", "vector": [0.1], "metadata": {"title": "T"}},
            ]
        )

    fake_coll.replace_one.assert_awaited_once()
    call = fake_coll.replace_one.await_args
    assert call.args[0] == {"_id": "1"}
    assert call.kwargs["upsert"] is True


@pytest.mark.asyncio
async def test_mongo_atlas_query_uses_vectorSearch():
    from largestack._vectorstores import MongoDBAtlasStore

    async def _agg_iter():
        yield {"_id": "1", "score": 0.95, "title": "A"}
        yield {"_id": "2", "score": 0.80, "title": "B"}

    fake_coll = MagicMock()
    # aggregate must return an async iterator
    fake_coll.aggregate = MagicMock(return_value=_agg_iter())

    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(return_value=fake_coll)
    fake_client = MagicMock()
    fake_client.__getitem__ = MagicMock(return_value=fake_db)
    fake_client.close = MagicMock()

    fake_motor = MagicMock()
    fake_motor.motor_asyncio.AsyncIOMotorClient = MagicMock(return_value=fake_client)

    with patch.dict(
        "sys.modules",
        {
            "motor": fake_motor,
            "motor.motor_asyncio": fake_motor.motor_asyncio,
        },
    ):
        store = MongoDBAtlasStore(uri="m", database="d", collection="c")
        results = await store.query([0.1, 0.2], top_k=5)

    assert len(results) == 2
    assert results[0]["id"] == "1"
    assert results[0]["score"] == 0.95
    assert results[0]["metadata"]["title"] == "A"

    # Verify pipeline structure
    pipeline = fake_coll.aggregate.call_args.args[0]
    assert "$vectorSearch" in pipeline[0]


# -------------------- Common interface --------------------


def test_all_new_stores_implement_vectorstore():
    from largestack._vectorstores import (
        VectorStore,
        MilvusStore,
        RedisVectorStore,
        ElasticsearchStore,
        OpenSearchStore,
        MongoDBAtlasStore,
    )

    assert issubclass(MilvusStore, VectorStore)
    assert issubclass(RedisVectorStore, VectorStore)
    assert issubclass(ElasticsearchStore, VectorStore)
    assert issubclass(OpenSearchStore, VectorStore)
    assert issubclass(MongoDBAtlasStore, VectorStore)
