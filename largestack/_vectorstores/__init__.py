"""Vector store adapters (v0.7.0).

Three production-grade adapters wrapping the official async clients:

- ``PineconeStore`` — uses ``pinecone[asyncio]`` (PineconeAsyncio, v8+)
- ``WeaviateStore`` — uses ``weaviate-client`` v4+ (WeaviateAsyncClient)
- ``PgVectorStore`` — uses ``asyncpg`` + the pgvector Postgres extension

All three implement the same ``VectorStore`` interface so they're
interchangeable from your agent's perspective:

    store = PineconeStore(index_name="my-idx", api_key="...")
    await store.upsert([{"id": "1", "vector": [...], "metadata": {...}}])
    results = await store.query(vector=[...], top_k=5)
    await store.delete(ids=["1", "2"])
    await store.close()

Or use as async context manager:

    async with PineconeStore(...) as store:
        await store.upsert([...])

Each adapter gracefully reports if its underlying client SDK isn't
installed — no errors during LARGESTACK startup if you don't use them.
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("largestack.vectorstores")


def _validate_metadata_key(name: str) -> str:
    """Validate metadata keys used in SQL JSON filter expressions."""
    import re

    if not isinstance(name, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"invalid metadata filter key: {name!r}")
    return name


def _validate_vector_dim(dim: int) -> int:
    """Validate vector dimensions used in SQL type declarations."""
    if not isinstance(dim, int) or dim <= 0 or dim > 100_000:
        raise ValueError(f"invalid vector dimension: {dim!r}")
    return dim


# -------------------- Common interface --------------------

class VectorStore:
    """Abstract interface — concrete impls below."""

    async def upsert(self, vectors: list[dict]) -> None:
        """Insert/update vectors. Each dict has id, vector, metadata."""
        raise NotImplementedError

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        """Search by vector. Returns list of {id, score, metadata}."""
        raise NotImplementedError

    async def delete(self, ids: list[str]) -> None:
        """Delete by IDs."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release resources."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()


# -------------------- Pinecone --------------------

class PineconeStore(VectorStore):
    """Pinecone vector store using PineconeAsyncio (pinecone v8+ asyncio).

    Auth: ``api_key`` argument or ``PINECONE_API_KEY`` env var.
    Requires: ``pip install pinecone[asyncio]``.

    Note: in Pinecone, you must create the index ahead of time (via
    console or another script) — this adapter operates on an existing index.
    """

    def __init__(
        self,
        index_name: str,
        api_key: str | None = None,
        host: str | None = None,
        namespace: str = "",
    ):
        self.index_name = index_name
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY", "")
        self.host = host
        self.namespace = namespace
        self._pc = None
        self._idx = None

    async def _connect(self):
        if self._idx is not None:
            return
        try:
            from pinecone import PineconeAsyncio
        except ImportError as e:
            raise ImportError(
                "PineconeStore needs: pip install 'pinecone[asyncio]'"
            ) from e
        if not self.api_key:
            raise ValueError(
                "PineconeStore: api_key arg or PINECONE_API_KEY env var required"
            )
        self._pc = PineconeAsyncio(api_key=self.api_key)
        # Resolve host if not provided
        if self.host is None:
            desc = await self._pc.describe_index(name=self.index_name)
            self.host = desc.host
        self._idx = self._pc.IndexAsyncio(host=self.host)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        # Pinecone wants format: [(id, vec, meta), ...] or list of dicts
        formatted = [
            {
                "id": str(v["id"]),
                "values": v["vector"],
                "metadata": v.get("metadata", {}),
            }
            for v in vectors
        ]
        kw: dict = {"vectors": formatted}
        if self.namespace:
            kw["namespace"] = self.namespace
        await self._idx.upsert(**kw)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        kw: dict = {
            "vector": vector,
            "top_k": top_k,
            "include_metadata": True,
        }
        if filter:
            kw["filter"] = filter
        if self.namespace:
            kw["namespace"] = self.namespace
        resp = await self._idx.query(**kw)
        matches = getattr(resp, "matches", None) or resp.get("matches", [])
        return [
            {
                "id": m.id if hasattr(m, "id") else m["id"],
                "score": float(m.score if hasattr(m, "score") else m["score"]),
                "metadata": dict(m.metadata if hasattr(m, "metadata") else m.get("metadata", {})),
            }
            for m in matches
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        kw: dict = {"ids": [str(i) for i in ids]}
        if self.namespace:
            kw["namespace"] = self.namespace
        await self._idx.delete(**kw)

    async def close(self) -> None:
        if self._idx is not None:
            try:
                await self._idx.close()
            except Exception:
                pass
            self._idx = None
        if self._pc is not None:
            try:
                await self._pc.close()
            except Exception:
                pass
            self._pc = None


# -------------------- Weaviate --------------------

class WeaviateStore(VectorStore):
    """Weaviate vector store using WeaviateAsyncClient (v4+).

    Requires: ``pip install weaviate-client>=4.7``.

    Args:
        collection: Weaviate collection (class) name. Must already exist.
        url: cluster URL (e.g. ``rAnD0m.weaviate.cloud``).
        api_key: API key for cloud (or ``WEAVIATE_API_KEY`` env var).
        host: hostname for self-hosted (default localhost).
        port: HTTP port (default 8080) for self-hosted.
        grpc_port: gRPC port (default 50051) for self-hosted.
    """

    def __init__(
        self,
        collection: str,
        *,
        url: str | None = None,
        api_key: str | None = None,
        host: str = "localhost",
        port: int = 8080,
        grpc_port: int = 50051,
    ):
        self.collection_name = collection
        self.url = url
        self.api_key = api_key or os.environ.get("WEAVIATE_API_KEY")
        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self._client = None
        self._collection = None

    async def _connect(self):
        if self._collection is not None:
            return
        try:
            import weaviate
            from weaviate.classes.init import Auth
        except ImportError as e:
            raise ImportError(
                "WeaviateStore needs: pip install 'weaviate-client>=4.7'"
            ) from e

        if self.url:
            # Cloud connection
            auth = Auth.api_key(self.api_key) if self.api_key else None
            self._client = weaviate.use_async_with_weaviate_cloud(
                cluster_url=self.url,
                auth_credentials=auth,
            )
        else:
            # Local
            self._client = weaviate.use_async_with_local(
                host=self.host, port=self.port, grpc_port=self.grpc_port,
            )
        await self._client.connect()
        self._collection = self._client.collections.use(self.collection_name)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        # Weaviate v4 batch insert
        for v in vectors:
            await self._collection.data.insert(
                uuid=str(v["id"]),
                properties=v.get("metadata", {}),
                vector=v["vector"],
            )

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        # Build filter if provided
        wvc_filter = None
        if filter:
            try:
                from weaviate.classes.query import Filter
                # Translate {"field": "value"} → Filter.by_property("field").equal("value")
                clauses = []
                for k, v in filter.items():
                    clauses.append(Filter.by_property(k).equal(v))
                wvc_filter = clauses[0] if len(clauses) == 1 else (
                    Filter.all_of(clauses) if hasattr(Filter, "all_of") else clauses[0]
                )
            except Exception as e:
                log.debug(f"weaviate filter build failed: {e}")

        kw: dict = {"near_vector": vector, "limit": top_k, "return_metadata": ["score", "distance"]}
        if wvc_filter is not None:
            kw["filters"] = wvc_filter
        resp = await self._collection.query.near_vector(**kw)
        return [
            {
                "id": str(o.uuid),
                "score": float(getattr(o.metadata, "score", 0.0) or 0.0),
                "metadata": dict(o.properties or {}),
            }
            for o in resp.objects
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        for i in ids:
            try:
                await self._collection.data.delete_by_id(str(i))
            except Exception as e:
                log.debug(f"weaviate delete {i} failed: {e}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
            self._collection = None


# -------------------- pgvector --------------------

class PgVectorStore(VectorStore):
    """Postgres + pgvector vector store using asyncpg.

    Requires: ``pip install asyncpg`` and a Postgres database with the
    ``pgvector`` extension installed (``CREATE EXTENSION vector;``).

    The table must have these columns at minimum:
        id TEXT PRIMARY KEY,
        embedding vector(N),
        metadata JSONB

    Args:
        dsn: Postgres connection string, e.g. ``postgres://user:pass@host/db``.
        table: table name (must already exist).
        dim: vector dimension (used for INSERT formatting only).
    """

    def __init__(
        self,
        dsn: str,
        table: str,
        dim: int = 1536,
    ):
        self.dsn = dsn
        self.table = self._validate_table(table)
        self.dim = _validate_vector_dim(dim)
        self._pool = None

    @staticmethod
    def _validate_table(name: str) -> str:
        # Defense against SQL injection — table name must be safe identifier
        import re
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"invalid table name: {name!r}")
        return name

    async def _connect(self):
        if self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError as e:
            raise ImportError("PgVectorStore needs: pip install asyncpg") from e
        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        import json as _json
        sql = (
            f"INSERT INTO {self.table} (id, embedding, metadata) "  # nosec B608
            f"VALUES ($1, $2::vector, $3::jsonb) "
            f"ON CONFLICT (id) DO UPDATE SET "
            f"embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata"
        )
        async with self._pool.acquire() as conn:
            for v in vectors:
                vec_str = "[" + ",".join(str(x) for x in v["vector"]) + "]"
                meta = _json.dumps(v.get("metadata", {}))
                await conn.execute(sql, str(v["id"]), vec_str, meta)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        vec_str = "[" + ",".join(str(float(x)) for x in vector) + "]"
        # Cosine distance: smaller is closer; convert to similarity
        params = [vec_str]
        where = ""
        if filter:
            # Equality filters on metadata JSONB; keys and values are parameterized.
            conds = []
            for k, v in filter.items():
                _validate_metadata_key(k)
                params.append(k)
                key_idx = len(params)
                params.append(str(v))
                value_idx = len(params)
                conds.append(f"metadata->>${key_idx} = ${value_idx}")
            where = " WHERE " + " AND ".join(conds)
        params.append(int(top_k))
        limit_idx = len(params)
        sql = (
            f"SELECT id, 1 - (embedding <=> $1::vector) AS score, metadata "  # nosec B608
            f"FROM {self.table}{where} "
            f"ORDER BY embedding <=> $1::vector "
            f"LIMIT ${limit_idx}"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        import json as _json
        return [
            {
                "id": r["id"],
                "score": float(r["score"]),
                "metadata": _json.loads(r["metadata"]) if isinstance(r["metadata"], str)
                else dict(r["metadata"] or {}),
            }
            for r in rows
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        sql = f"DELETE FROM {self.table} WHERE id = ANY($1::text[])"  # nosec B608
        async with self._pool.acquire() as conn:
            await conn.execute(sql, [str(i) for i in ids])

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


# -------------------- Milvus (v0.8.0) --------------------

class MilvusStore(VectorStore):
    """Milvus vector store using pymilvus async API.

    Requires: ``pip install pymilvus>=2.4`` (current as of 2026).

    Args:
        collection: Milvus collection name (must already exist).
        uri: Milvus server URI, e.g. ``"http://localhost:19530"`` or
            ``"https://in03-xxx.api.gcp-us-west1.zillizcloud.com"`` for
            Zilliz Cloud.
        token: API token for Zilliz Cloud (or ``user:password`` for OSS).
        dim: vector dimension (informational; the collection determines actual).
    """

    def __init__(
        self,
        collection: str,
        *,
        uri: str = "http://localhost:19530",
        token: str | None = None,
        dim: int = 1536,
    ):
        self.collection_name = collection
        self.uri = uri
        self.token = token or os.environ.get("MILVUS_TOKEN")
        self.dim = dim
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from pymilvus import AsyncMilvusClient
        except ImportError as e:
            raise ImportError(
                "MilvusStore needs: pip install 'pymilvus>=2.4'"
            ) from e
        kw: dict = {"uri": self.uri}
        if self.token:
            kw["token"] = self.token
        self._client = AsyncMilvusClient(**kw)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        data = [
            {
                "id": v["id"],
                "vector": v["vector"],
                "metadata": v.get("metadata", {}),
            }
            for v in vectors
        ]
        await self._client.upsert(collection_name=self.collection_name, data=data)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        kw: dict = {
            "collection_name": self.collection_name,
            "data": [vector],
            "limit": top_k,
            "output_fields": ["metadata"],
        }
        if filter:
            # Milvus expression syntax: 'field == "value"'
            conds = []
            for k, v in filter.items():
                if isinstance(v, str):
                    conds.append(f'metadata["{k}"] == "{v}"')
                else:
                    conds.append(f'metadata["{k}"] == {v}')
            if conds:
                kw["filter"] = " and ".join(conds)
        results = await self._client.search(**kw)
        # results is a list of lists (one per query vector); we sent 1 query
        first = results[0] if results else []
        return [
            {
                "id": str(r.get("id", r.get("pk", ""))),
                "score": float(r.get("distance", 0.0)),
                "metadata": dict(r.get("entity", {}).get("metadata") or r.get("metadata", {}) or {}),
            }
            for r in first
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        await self._client.delete(
            collection_name=self.collection_name,
            ids=[str(i) for i in ids],
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# -------------------- Redis Vector (v0.8.0) --------------------

class RedisVectorStore(VectorStore):
    """Redis Stack vector store using redis-py async (4.5+).

    Requires: ``pip install redis>=5.0`` and Redis Stack (or RediSearch
    module). Index must already exist with FT.CREATE.

    Args:
        url: Redis URL, e.g. ``"redis://localhost:6379"``.
        index_name: existing FT index name.
        key_prefix: hash key prefix (e.g. ``"doc:"``).
        vector_field: name of the VECTOR field (default ``"embedding"``).
    """

    def __init__(
        self,
        url: str,
        index_name: str,
        *,
        key_prefix: str = "doc:",
        vector_field: str = "embedding",
    ):
        self.url = url
        self.index_name = index_name
        self.key_prefix = key_prefix
        self.vector_field = vector_field
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            import redis.asyncio as redis_async
        except ImportError as e:
            raise ImportError("RedisVectorStore needs: pip install 'redis>=5.0'") from e
        self._client = redis_async.from_url(self.url, decode_responses=False)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        import struct
        for v in vectors:
            key = f"{self.key_prefix}{v['id']}"
            vec_bytes = struct.pack(f"{len(v['vector'])}f", *v["vector"])
            mapping: dict = {self.vector_field: vec_bytes}
            for mk, mv in (v.get("metadata") or {}).items():
                if isinstance(mv, (str, int, float)):
                    mapping[mk] = str(mv)
            await self._client.hset(key, mapping=mapping)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        import struct
        vec_bytes = struct.pack(f"{len(vector)}f", *vector)
        # KNN query syntax: '*=>[KNN k @field $V AS score]'
        filter_str = "*"
        if filter:
            parts = [f"@{k}:{{{v}}}" for k, v in filter.items()]
            filter_str = " ".join(parts)
        query_str = f"({filter_str})=>[KNN {top_k} @{self.vector_field} $vec AS score]"
        # Use raw FT.SEARCH command
        try:
            raw = await self._client.execute_command(
                "FT.SEARCH", self.index_name, query_str,
                "PARAMS", "2", "vec", vec_bytes,
                "DIALECT", "2",
                "SORTBY", "score", "ASC",
                "LIMIT", "0", str(top_k),
            )
        except Exception as e:
            log.debug(f"Redis FT.SEARCH failed: {e}")
            return []
        # Response format: [count, key1, [field1, val1, ...], key2, [...], ...]
        results = []
        if not isinstance(raw, list) or len(raw) < 1:
            return []
        for i in range(1, len(raw), 2):
            if i + 1 >= len(raw):
                break
            key = raw[i].decode() if isinstance(raw[i], bytes) else raw[i]
            doc_id = key[len(self.key_prefix):] if key.startswith(self.key_prefix) else key
            fields_arr = raw[i + 1] or []
            fields: dict = {}
            for j in range(0, len(fields_arr), 2):
                if j + 1 >= len(fields_arr):
                    break
                fk = fields_arr[j].decode() if isinstance(fields_arr[j], bytes) else fields_arr[j]
                fv = fields_arr[j + 1]
                if isinstance(fv, bytes):
                    try:
                        fv = fv.decode()
                    except UnicodeDecodeError:
                        fv = "<binary>"
                fields[fk] = fv
            score = float(fields.pop("score", 0.0))
            fields.pop(self.vector_field, None)  # drop embedding bytes
            results.append({"id": doc_id, "score": score, "metadata": fields})
        return results

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        keys = [f"{self.key_prefix}{i}" for i in ids]
        if keys:
            await self._client.delete(*keys)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


# -------------------- Elasticsearch (v0.8.0) --------------------

class ElasticsearchStore(VectorStore):
    """Elasticsearch vector store using elasticsearch-py async (8+).

    Requires: ``pip install 'elasticsearch[async]>=8.0'``.

    Args:
        index: index name (must exist with a dense_vector mapping).
        hosts: list of ES URLs e.g. ``["https://localhost:9200"]``.
        api_key: API key (optional; alternatively use basic_auth).
        basic_auth: ``(username, password)`` tuple (optional).
        vector_field: dense_vector field name (default ``"embedding"``).
    """

    def __init__(
        self,
        index: str,
        *,
        hosts: list[str] | None = None,
        api_key: str | None = None,
        basic_auth: tuple[str, str] | None = None,
        vector_field: str = "embedding",
    ):
        self.index = index
        self.hosts = hosts or ["https://localhost:9200"]
        self.api_key = api_key
        self.basic_auth = basic_auth
        self.vector_field = vector_field
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as e:
            raise ImportError(
                "ElasticsearchStore needs: pip install 'elasticsearch[async]>=8.0'"
            ) from e
        kw: dict = {"hosts": self.hosts}
        if self.api_key:
            kw["api_key"] = self.api_key
        if self.basic_auth:
            kw["basic_auth"] = self.basic_auth
        self._client = AsyncElasticsearch(**kw)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        for v in vectors:
            doc: dict = {self.vector_field: v["vector"]}
            for mk, mv in (v.get("metadata") or {}).items():
                doc[mk] = mv
            await self._client.index(index=self.index, id=str(v["id"]), document=doc)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        knn_query: dict = {
            "field": self.vector_field,
            "query_vector": vector,
            "k": top_k,
            "num_candidates": max(top_k * 4, 100),
        }
        if filter:
            knn_query["filter"] = {
                "bool": {
                    "must": [{"term": {k: v}} for k, v in filter.items()]
                }
            }
        resp = await self._client.search(
            index=self.index, knn=knn_query, size=top_k,
        )
        hits = (resp.get("hits") or {}).get("hits") or []
        return [
            {
                "id": str(h.get("_id", "")),
                "score": float(h.get("_score", 0.0)),
                "metadata": {
                    k: v for k, v in (h.get("_source") or {}).items()
                    if k != self.vector_field
                },
            }
            for h in hits
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        for i in ids:
            try:
                await self._client.delete(index=self.index, id=str(i))
            except Exception as e:
                log.debug(f"ES delete {i} failed: {e}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# -------------------- OpenSearch (v0.8.0) --------------------

class OpenSearchStore(VectorStore):
    """OpenSearch vector store using opensearch-py async.

    Requires: ``pip install 'opensearch-py>=2.4'``.

    Same interface as ElasticsearchStore but uses OpenSearch's KNN plugin.

    Args:
        index: index name (must exist with a knn_vector mapping).
        hosts: list of OS URLs.
        http_auth: ``(username, password)`` (optional).
        vector_field: knn_vector field name (default ``"embedding"``).
    """

    def __init__(
        self,
        index: str,
        *,
        hosts: list[str] | None = None,
        http_auth: tuple[str, str] | None = None,
        vector_field: str = "embedding",
        use_ssl: bool = True,
    ):
        self.index = index
        self.hosts = hosts or ["https://localhost:9200"]
        self.http_auth = http_auth
        self.vector_field = vector_field
        self.use_ssl = use_ssl
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from opensearchpy import AsyncOpenSearch
        except ImportError as e:
            raise ImportError(
                "OpenSearchStore needs: pip install 'opensearch-py>=2.4'"
            ) from e
        kw: dict = {"hosts": self.hosts, "use_ssl": self.use_ssl}
        if self.http_auth:
            kw["http_auth"] = self.http_auth
        self._client = AsyncOpenSearch(**kw)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        for v in vectors:
            doc: dict = {self.vector_field: v["vector"]}
            for mk, mv in (v.get("metadata") or {}).items():
                doc[mk] = mv
            await self._client.index(index=self.index, id=str(v["id"]), body=doc)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        knn = {
            "size": top_k,
            "query": {
                "knn": {
                    self.vector_field: {"vector": vector, "k": top_k}
                }
            },
        }
        if filter:
            knn = {
                "size": top_k,
                "query": {
                    "bool": {
                        "must": [
                            {"knn": {self.vector_field: {"vector": vector, "k": top_k}}}
                        ],
                        "filter": [{"term": {k: v}} for k, v in filter.items()],
                    }
                },
            }
        resp = await self._client.search(index=self.index, body=knn)
        hits = (resp.get("hits") or {}).get("hits") or []
        return [
            {
                "id": str(h.get("_id", "")),
                "score": float(h.get("_score", 0.0)),
                "metadata": {
                    k: v for k, v in (h.get("_source") or {}).items()
                    if k != self.vector_field
                },
            }
            for h in hits
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        for i in ids:
            try:
                await self._client.delete(index=self.index, id=str(i))
            except Exception as e:
                log.debug(f"OpenSearch delete {i} failed: {e}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# -------------------- MongoDB Atlas Vector (v0.8.0) --------------------

class MongoDBAtlasStore(VectorStore):
    """MongoDB Atlas Vector Search using motor (async pymongo).

    Requires: ``pip install motor>=3.5`` and a MongoDB Atlas cluster
    with a Vector Search index already created on the target collection.

    Args:
        uri: MongoDB connection string.
        database: database name.
        collection: collection name.
        index_name: name of the Atlas Vector Search index.
        vector_field: field storing the embedding (default ``"embedding"``).
    """

    def __init__(
        self,
        uri: str,
        database: str,
        collection: str,
        *,
        index_name: str = "vector_index",
        vector_field: str = "embedding",
    ):
        self.uri = uri
        self.database = database
        self.collection_name = collection
        self.index_name = index_name
        self.vector_field = vector_field
        self._client = None
        self._coll = None

    async def _connect(self):
        if self._coll is not None:
            return
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            raise ImportError("MongoDBAtlasStore needs: pip install 'motor>=3.5'") from e
        self._client = AsyncIOMotorClient(self.uri)
        self._coll = self._client[self.database][self.collection_name]

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        for v in vectors:
            doc: dict = {
                "_id": str(v["id"]),
                self.vector_field: v["vector"],
                **(v.get("metadata") or {}),
            }
            await self._coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        pipeline: list = [
            {
                "$vectorSearch": {
                    "index": self.index_name,
                    "path": self.vector_field,
                    "queryVector": vector,
                    "numCandidates": max(top_k * 10, 100),
                    "limit": top_k,
                }
            },
            {
                "$project": {
                    self.vector_field: 0,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        if filter:
            pipeline[0]["$vectorSearch"]["filter"] = filter

        results = []
        async for doc in self._coll.aggregate(pipeline):
            results.append({
                "id": str(doc.pop("_id", "")),
                "score": float(doc.pop("score", 0.0)),
                "metadata": doc,  # whatever's left
            })
        return results

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        await self._coll.delete_many({"_id": {"$in": [str(i) for i in ids]}})

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()  # motor client.close() is sync
            self._client = None
            self._coll = None


# -------------------- Chroma (v0.9.0) --------------------

class ChromaStore(VectorStore):
    """Chroma vector store using chromadb async API.

    Requires: ``pip install chromadb>=0.5``.

    Args:
        collection: collection name (created if not exists).
        persist_directory: path for persistent storage (else in-memory).
        host: chromadb server host (for client-server mode).
        port: chromadb server port.
    """

    def __init__(
        self,
        collection: str,
        *,
        persist_directory: str | None = None,
        host: str | None = None,
        port: int = 8000,
    ):
        self.collection_name = collection
        self.persist_directory = persist_directory
        self.host = host
        self.port = port
        self._client = None
        self._coll = None

    async def _connect(self):
        if self._coll is not None:
            return
        try:
            import chromadb
        except ImportError as e:
            raise ImportError("ChromaStore needs: pip install 'chromadb>=0.5'") from e
        if self.host:
            self._client = await chromadb.AsyncHttpClient(host=self.host, port=self.port)
        elif self.persist_directory:
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            self._client = chromadb.Client()
        # get_or_create_collection is sync on PersistentClient/Client
        if hasattr(self._client, "get_or_create_collection"):
            res = self._client.get_or_create_collection(name=self.collection_name)
            if hasattr(res, "__await__"):
                self._coll = await res
            else:
                self._coll = res

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        ids = [str(v["id"]) for v in vectors]
        embeddings = [v["vector"] for v in vectors]
        metadatas = [v.get("metadata", {}) for v in vectors]
        documents = [str(v.get("metadata", {}).get("content", "")) for v in vectors]
        try:
            res = self._coll.upsert(
                ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents,
            )
            if hasattr(res, "__await__"):
                await res
        except Exception as e:
            log.debug(f"Chroma upsert failed: {e}")

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        kw: dict = {"query_embeddings": [vector], "n_results": top_k}
        if filter:
            kw["where"] = filter
        try:
            res = self._coll.query(**kw)
            if hasattr(res, "__await__"):
                res = await res
        except Exception as e:
            log.debug(f"Chroma query failed: {e}")
            return []
        ids = (res.get("ids") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        return [
            {
                "id": str(i),
                "score": 1.0 - float(d),  # convert distance to similarity
                "metadata": dict(m or {}),
            }
            for i, d, m in zip(ids, distances, metadatas)
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        try:
            res = self._coll.delete(ids=[str(i) for i in ids])
            if hasattr(res, "__await__"):
                await res
        except Exception as e:
            log.debug(f"Chroma delete failed: {e}")

    async def close(self) -> None:
        self._client = None
        self._coll = None


# -------------------- LanceDB (v0.9.0) --------------------

class LanceDBStore(VectorStore):
    """LanceDB embedded vector store using lancedb async client.

    Requires: ``pip install lancedb>=0.13``.

    Args:
        uri: directory path or s3://... URI for the LanceDB store.
        table: table name (created on first upsert if not exists).
        dim: vector dimension (used for table creation).
    """

    def __init__(self, uri: str, table: str, *, dim: int = 1536):
        self.uri = uri
        self.table_name = table
        self.dim = dim
        self._db = None
        self._table = None

    async def _connect(self):
        if self._table is not None:
            return
        try:
            import lancedb
        except ImportError as e:
            raise ImportError("LanceDBStore needs: pip install 'lancedb>=0.13'") from e
        self._db = await lancedb.connect_async(self.uri)
        try:
            self._table = await self._db.open_table(self.table_name)
        except Exception:
            # Create empty table with schema
            import pyarrow as pa
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.dim)),
                pa.field("metadata", pa.string()),
            ])
            self._table = await self._db.create_table(self.table_name, schema=schema)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        import json as _json
        records = [
            {
                "id": str(v["id"]),
                "vector": v["vector"],
                "metadata": _json.dumps(v.get("metadata", {})),
            }
            for v in vectors
        ]
        # LanceDB uses merge_insert for upsert
        try:
            mi = self._table.merge_insert("id")
            mi = mi.when_matched_update_all().when_not_matched_insert_all()
            await mi.execute(records)
        except AttributeError:
            await self._table.add(records)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        import json as _json
        try:
            q = self._table.search(vector).limit(top_k)
            if filter:
                # LanceDB SQL-like where clause
                conds = " AND ".join(
                    f"metadata LIKE '%\"{k}\":\"{v}\"%'" for k, v in filter.items()
                )
                q = q.where(conds)
            results = await q.to_list()
        except Exception as e:
            log.debug(f"LanceDB query failed: {e}")
            return []
        out = []
        for r in results:
            try:
                meta = _json.loads(r.get("metadata", "{}"))
            except Exception:
                meta = {}
            out.append({
                "id": str(r.get("id", "")),
                "score": 1.0 - float(r.get("_distance", 0.0)),
                "metadata": meta,
            })
        return out

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        if not ids:
            return
        ids_str = ", ".join(f"'{str(i)}'" for i in ids)
        await self._table.delete(f"id IN ({ids_str})")

    async def close(self) -> None:
        self._table = None
        self._db = None


# -------------------- Azure Cognitive Search (v0.9.0) --------------------

class AzureCognitiveSearchStore(VectorStore):
    """Azure AI Search (formerly Cognitive Search) vector store.

    Requires: ``pip install azure-search-documents>=11.4``.

    Args:
        endpoint: search service endpoint (e.g. ``https://x.search.windows.net``).
        index_name: existing index name with vector field configured.
        api_key: admin API key (or use AzureKeyCredential).
        vector_field: name of the Collection(Edm.Single) vector field.
    """

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        *,
        api_key: str | None = None,
        vector_field: str = "embedding",
    ):
        self.endpoint = endpoint
        self.index_name = index_name
        self.api_key = api_key or os.environ.get("AZURE_SEARCH_API_KEY")
        self.vector_field = vector_field
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from azure.search.documents.aio import SearchClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as e:
            raise ImportError(
                "AzureCognitiveSearchStore needs: pip install 'azure-search-documents>=11.4'"
            ) from e
        if not self.api_key:
            raise ValueError("Azure Search api_key required (or AZURE_SEARCH_API_KEY env var)")
        self._client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key),
        )

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        docs = []
        for v in vectors:
            doc: dict = {
                "id": str(v["id"]),
                self.vector_field: v["vector"],
            }
            for mk, mv in (v.get("metadata") or {}).items():
                doc[mk] = mv
            docs.append(doc)
        await self._client.upload_documents(documents=docs)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        await self._connect()
        try:
            from azure.search.documents.models import VectorizedQuery
        except ImportError:
            return [{"error": "azure-search-documents needs upgrade"}]
        vq = VectorizedQuery(
            vector=vector, k_nearest_neighbors=top_k, fields=self.vector_field,
        )
        kw: dict = {"vector_queries": [vq], "top": top_k}
        if filter:
            # OData filter syntax
            kw["filter"] = " and ".join(f"{k} eq '{v}'" for k, v in filter.items())
        results = []
        async for r in await self._client.search(search_text=None, **kw):
            row = dict(r)
            score = float(row.pop("@search.score", 0.0))
            row.pop(self.vector_field, None)
            results.append({
                "id": str(row.pop("id", "")),
                "score": score,
                "metadata": row,
            })
        return results

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        await self._client.delete_documents(
            documents=[{"id": str(i)} for i in ids]
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# -------------------- Supabase Vector (v0.9.0) --------------------

class SupabaseVectorStore(PgVectorStore):
    """Supabase Vector — convenience wrapper over pgvector.

    Supabase uses pgvector under the hood with their own client.
    This wrapper accepts a Supabase URL + anon/service key and constructs
    the appropriate Postgres connection string automatically.

    Args:
        supabase_url: e.g. ``https://abc.supabase.co``.
        password: Postgres password (Settings → Database).
        table: table name with embedding column.
        dim: vector dimension.
    """

    def __init__(
        self,
        supabase_url: str,
        password: str,
        table: str,
        *,
        dim: int = 1536,
        host_override: str | None = None,
    ):
        # Build Postgres DSN from Supabase URL
        # Supabase pattern: db.{project_ref}.supabase.co
        host = host_override
        if host is None:
            from urllib.parse import urlparse
            parsed = urlparse(supabase_url)
            host_part = parsed.hostname or ""
            project_ref = host_part.split(".")[0]
            if project_ref and not project_ref.startswith("db."):
                host = f"db.{project_ref}.supabase.co"
            else:
                host = host_part
        dsn = f"postgresql://postgres:{password}@{host}:5432/postgres"
        super().__init__(dsn=dsn, table=table, dim=dim)


# -------------------- FAISS Persistent (v0.9.0) --------------------

class FaissPersistentStore(VectorStore):
    """FAISS vector store with disk persistence.

    Existing LARGESTACK FAISS support is in-memory only. This adapter saves
    and loads the index from disk so embeddings survive restarts.

    Requires: ``pip install faiss-cpu`` (or faiss-gpu).

    Args:
        index_path: path to the .faiss index file.
        meta_path: path to the .json sidecar with id+metadata mapping.
        dim: embedding dimension.
        metric: ``"cosine"`` (default), ``"l2"``, or ``"ip"``.
    """

    def __init__(
        self,
        index_path: str,
        meta_path: str,
        *,
        dim: int = 1536,
        metric: str = "cosine",
    ):
        self.index_path = index_path
        self.meta_path = meta_path
        self.dim = dim
        self.metric = metric
        self._index = None
        self._meta: dict = {}
        self._id_to_idx: dict = {}
        self._next_idx = 0

    def _load_or_create(self):
        if self._index is not None:
            return
        try:
            import faiss
        except ImportError as e:
            raise ImportError("FaissPersistentStore needs: pip install faiss-cpu") from e
        import json as _json
        if os.path.exists(self.index_path):
            self._index = faiss.read_index(self.index_path)
        else:
            if self.metric == "cosine" or self.metric == "ip":
                self._index = faiss.IndexFlatIP(self.dim)
            else:
                self._index = faiss.IndexFlatL2(self.dim)
            # Wrap in IDMap so we can use external IDs
            self._index = faiss.IndexIDMap(self._index)
        if os.path.exists(self.meta_path):
            with open(self.meta_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            self._meta = data.get("meta", {})
            self._id_to_idx = data.get("id_to_idx", {})
            self._next_idx = int(data.get("next_idx", 0))

    def _save(self):
        import faiss
        import json as _json
        faiss.write_index(self._index, self.index_path)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            _json.dump({
                "meta": self._meta,
                "id_to_idx": self._id_to_idx,
                "next_idx": self._next_idx,
            }, f)

    async def upsert(self, vectors: list[dict]) -> None:
        await asyncio.to_thread(self._upsert_sync, vectors)

    def _upsert_sync(self, vectors: list[dict]) -> None:
        self._load_or_create()
        import numpy as np
        for v in vectors:
            doc_id = str(v["id"])
            arr = np.asarray(v["vector"], dtype=np.float32).reshape(1, -1)
            if self.metric == "cosine":
                # Normalize for cosine via inner product
                norm = np.linalg.norm(arr)
                if norm > 0:
                    arr = arr / norm
            if doc_id in self._id_to_idx:
                # Remove existing then re-add (FAISS doesn't support update directly)
                self._index.remove_ids(np.array([self._id_to_idx[doc_id]], dtype=np.int64))
            idx = self._next_idx
            self._next_idx += 1
            self._index.add_with_ids(arr, np.array([idx], dtype=np.int64))
            self._id_to_idx[doc_id] = idx
            self._meta[str(idx)] = {
                "id": doc_id,
                "metadata": v.get("metadata", {}),
            }
        self._save()

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        return await asyncio.to_thread(self._query_sync, vector, top_k, filter)

    def _query_sync(
        self, vector: list[float], top_k: int, filter: dict | None
    ) -> list[dict]:
        self._load_or_create()
        import numpy as np
        if self._index.ntotal == 0:
            return []
        arr = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if self.metric == "cosine":
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
        # Get more if filter applied to allow post-filtering
        search_k = top_k * (5 if filter else 1)
        distances, indices = self._index.search(arr, search_k)
        out = []
        for d, i in zip(distances[0], indices[0]):
            if i == -1:
                continue
            entry = self._meta.get(str(i), {})
            md = entry.get("metadata", {})
            if filter:
                if not all(md.get(k) == v for k, v in filter.items()):
                    continue
            out.append({
                "id": entry.get("id", str(i)),
                "score": float(d),
                "metadata": md,
            })
            if len(out) >= top_k:
                break
        return out

    async def delete(self, ids: list[str]) -> None:
        await asyncio.to_thread(self._delete_sync, ids)

    def _delete_sync(self, ids: list[str]) -> None:
        self._load_or_create()
        import numpy as np
        idxs = []
        for doc_id in ids:
            idx = self._id_to_idx.pop(str(doc_id), None)
            if idx is not None:
                idxs.append(idx)
                self._meta.pop(str(idx), None)
        if idxs:
            self._index.remove_ids(np.array(idxs, dtype=np.int64))
        self._save()

    async def close(self) -> None:
        if self._index is not None:
            await asyncio.to_thread(self._save)
            self._index = None


# -------------------- DuckDB Vector (v0.9.0) --------------------

class DuckDBVectorStore(VectorStore):
    """DuckDB vector store using the vss extension.

    Requires: ``pip install duckdb>=0.10`` (with vss available via INSTALL vss).

    Best for: analytics-heavy workloads where you want to JOIN vector
    similarity with regular SQL on the same data.

    Args:
        db_path: path to DuckDB file (or ``":memory:"`` for in-mem).
        table: table name (created if not exists).
        dim: embedding dimension.
    """

    def __init__(self, db_path: str, table: str, *, dim: int = 1536):
        self.db_path = db_path
        self.table_name = self._validate_table(table)
        self.dim = _validate_vector_dim(dim)
        self._conn = None

    @staticmethod
    def _validate_table(name: str) -> str:
        import re
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"invalid table name: {name!r}")
        return name

    async def _connect(self):
        if self._conn is not None:
            return
        await asyncio.to_thread(self._connect_sync)

    def _connect_sync(self):
        try:
            import duckdb
        except ImportError as e:
            raise ImportError("DuckDBVectorStore needs: pip install 'duckdb>=0.10'") from e
        self._conn = duckdb.connect(self.db_path)
        # Install + load vss extension (vector similarity search)
        try:
            self._conn.execute("INSTALL vss")
            self._conn.execute("LOAD vss")
        except Exception as e:
            log.debug(f"DuckDB vss extension unavailable: {e}")
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ("  # nosec B608
            f"id VARCHAR PRIMARY KEY, "
            f"embedding FLOAT[{self.dim}], "
            f"metadata JSON"
            f")"
        )

    async def upsert(self, vectors: list[dict]) -> None:
        await asyncio.to_thread(self._upsert_sync, vectors)

    def _upsert_sync(self, vectors: list[dict]):
        self._connect_sync()
        import json as _json
        for v in vectors:
            self._conn.execute(
                f"INSERT OR REPLACE INTO {self.table_name} (id, embedding, metadata) "  # nosec B608
                f"VALUES (?, ?, ?)",
                (str(v["id"]), v["vector"], _json.dumps(v.get("metadata", {}))),
            )

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None
    ) -> list[dict]:
        return await asyncio.to_thread(self._query_sync, vector, top_k, filter)

    def _query_sync(
        self, vector: list[float], top_k: int, filter: dict | None
    ) -> list[dict]:
        self._connect_sync()
        import json as _json
        where = ""
        params: list = [vector, vector]
        if filter:
            conds = []
            for k, v in filter.items():
                _validate_metadata_key(k)
                conds.append("json_extract_string(metadata, ?) = ?")
                params.extend([f"$.{k}", str(v)])
            where = " WHERE " + " AND ".join(conds)
        params.append(int(top_k))
        sql = (
            f"SELECT id, "  # nosec B608
            f"array_cosine_similarity(embedding, ?::FLOAT[{self.dim}]) AS score, "
            f"metadata FROM {self.table_name}{where} "
            f"ORDER BY array_cosine_similarity(embedding, ?::FLOAT[{self.dim}]) DESC "
            f"LIMIT ?"
        )
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except Exception as e:
            # Fallback if array_cosine_similarity not available
            log.debug(f"DuckDB cosine query failed, fallback: {e}")
            return []
        out = []
        for row in rows:
            doc_id, score, meta_json = row
            try:
                meta = _json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            out.append({"id": doc_id, "score": float(score or 0.0), "metadata": meta})
        return out

    async def delete(self, ids: list[str]) -> None:
        await asyncio.to_thread(self._delete_sync, ids)

    def _delete_sync(self, ids: list[str]):
        self._connect_sync()
        for i in ids:
            self._conn.execute(
                f"DELETE FROM {self.table_name} WHERE id = ?",  # nosec B608
                (str(i),),
            )

    async def close(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.close)
            self._conn = None


# -------------------- Aurora Postgres pgvector (v0.9.0) --------------------

class AuroraPgVectorStore(PgVectorStore):
    """AWS Aurora Postgres with pgvector — convenience wrapper.

    Aurora uses standard Postgres protocol, so this just calls through
    to ``PgVectorStore`` with proper IAM auth detection.

    Args:
        cluster_endpoint: Aurora cluster endpoint (...rds.amazonaws.com).
        database: db name.
        username: Postgres user.
        password: Postgres password (or use IAM auth via boto3).
        port: default 5432.
        table: vector table name.
        dim: embedding dimension.
        ssl: ``True`` to require SSL (recommended for Aurora).
    """

    def __init__(
        self,
        cluster_endpoint: str,
        database: str,
        username: str,
        password: str,
        table: str,
        *,
        port: int = 5432,
        dim: int = 1536,
        ssl: bool = True,
    ):
        sslmode = "require" if ssl else "prefer"
        dsn = (
            f"postgresql://{username}:{password}@{cluster_endpoint}:{port}/"
            f"{database}?sslmode={sslmode}"
        )
        super().__init__(dsn=dsn, table=table, dim=dim)
        self.cluster_endpoint = cluster_endpoint


# -------------------- MongoDB Atlas Vector Search (v0.10.0) --------------------

class MongoAtlasVectorStore(VectorStore):
    """MongoDB Atlas Vector Search — Mongo's native vector index.

    Different from the existing ``MongoVectorStore`` (which stores arrays
    as fields and does cosine in Python). Atlas Vector Search uses a
    real ANN index defined in the cluster's Atlas Search config.

    Requires:
    - MongoDB Atlas cluster with Atlas Search enabled
    - A vector search index defined on the collection (created in Atlas UI)
    - ``pip install motor>=3.0``

    Args:
        uri: ``mongodb+srv://user:pw@cluster.mongodb.net``
        database: db name
        collection: collection name
        index_name: name of the Atlas vector search index
        vector_field: name of the field holding the embedding (default: ``embedding``)
        dim: vector dimension
    """

    def __init__(
        self,
        uri: str,
        database: str,
        collection: str,
        *,
        index_name: str = "vector_index",
        vector_field: str = "embedding",
        dim: int = 1536,
    ):
        self.uri = uri
        self.database_name = database
        self.collection_name = collection
        self.index_name = index_name
        self.vector_field = vector_field
        self.dim = dim
        self._client = None
        self._coll = None

    async def _connect(self):
        if self._coll is not None:
            return
        try:
            import motor.motor_asyncio
        except ImportError as e:
            raise ImportError(
                "MongoAtlasVectorStore needs: pip install 'motor>=3.0'"
            ) from e
        self._client = motor.motor_asyncio.AsyncIOMotorClient(self.uri)
        self._coll = self._client[self.database_name][self.collection_name]

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        from pymongo import UpdateOne
        ops = []
        for v in vectors:
            doc = {
                "_id": str(v["id"]),
                self.vector_field: v["vector"],
                "metadata": v.get("metadata", {}),
            }
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))
        if ops:
            await self._coll.bulk_write(ops)

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None,
    ) -> list[dict]:
        await self._connect()
        # $vectorSearch aggregation stage (Atlas-native)
        stage: dict = {
            "$vectorSearch": {
                "index": self.index_name,
                "path": self.vector_field,
                "queryVector": vector,
                "numCandidates": max(top_k * 10, 100),
                "limit": top_k,
            }
        }
        if filter:
            # Convert simple filter dict into MQL filter at metadata.* path
            mql_filter = {f"metadata.{k}": v for k, v in filter.items()}
            stage["$vectorSearch"]["filter"] = mql_filter

        pipeline = [
            stage,
            {"$project": {
                "_id": 1, "metadata": 1,
                "score": {"$meta": "vectorSearchScore"},
            }},
        ]
        try:
            cursor = self._coll.aggregate(pipeline)
            results = []
            async for doc in cursor:
                results.append({
                    "id": str(doc.get("_id", "")),
                    "score": float(doc.get("score", 0.0)),
                    "metadata": doc.get("metadata", {}),
                })
            return results
        except Exception as e:
            log.debug(f"MongoAtlas $vectorSearch failed: {e}")
            return []

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        if not ids:
            return
        await self._coll.delete_many({"_id": {"$in": [str(i) for i in ids]}})

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._coll = None


# -------------------- Elasticsearch dense_vector (v0.10.0) --------------------

class ElasticsearchDenseVectorStore(VectorStore):
    """Elasticsearch dense_vector field with kNN search.

    Uses ES native ``dense_vector`` field type and ``knn`` search clause.
    Works with Elasticsearch 8.0+ (where ``dense_vector`` got proper
    ANN support via HNSW).

    Requires:
    - Elasticsearch 8.0+ cluster
    - An index with a ``dense_vector`` field defined (created externally)
    - ``pip install elasticsearch[async]>=8.0``

    Args:
        hosts: list of ES URLs (e.g. ``["https://localhost:9200"]``)
        index: ES index name
        vector_field: name of the dense_vector field (default: ``embedding``)
        dim: vector dimension
        api_key: optional API key (or basic_auth tuple)
    """

    def __init__(
        self,
        hosts: list[str] | str,
        index: str,
        *,
        vector_field: str = "embedding",
        dim: int = 1536,
        api_key: str | None = None,
        basic_auth: tuple[str, str] | None = None,
    ):
        self.hosts = hosts if isinstance(hosts, list) else [hosts]
        self.index_name = index
        self.vector_field = vector_field
        self.dim = dim
        self.api_key = api_key or os.environ.get("ELASTIC_API_KEY")
        self.basic_auth = basic_auth
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as e:
            raise ImportError(
                "ElasticsearchDenseVectorStore needs: "
                "pip install 'elasticsearch[async]>=8.0'"
            ) from e
        kwargs: dict = {"hosts": self.hosts}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        elif self.basic_auth:
            kwargs["basic_auth"] = self.basic_auth
        self._client = AsyncElasticsearch(**kwargs)

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        # Use _bulk for efficiency
        operations = []
        for v in vectors:
            doc_id = str(v["id"])
            operations.append({"index": {"_index": self.index_name, "_id": doc_id}})
            doc: dict = {
                self.vector_field: v["vector"],
                "metadata": v.get("metadata", {}),
            }
            operations.append(doc)
        if operations:
            try:
                await self._client.bulk(operations=operations, refresh=False)
            except Exception as e:
                log.debug(f"ES bulk upsert failed: {e}")

    async def query(
        self, vector: list[float], top_k: int = 5, filter: dict | None = None,
    ) -> list[dict]:
        await self._connect()
        knn: dict = {
            "field": self.vector_field,
            "query_vector": vector,
            "k": top_k,
            "num_candidates": max(top_k * 10, 100),
        }
        if filter:
            # Pre-filter via term clauses on metadata.*
            knn["filter"] = {
                "bool": {
                    "must": [
                        {"term": {f"metadata.{k}": v}}
                        for k, v in filter.items()
                    ]
                }
            }
        try:
            resp = await self._client.search(
                index=self.index_name,
                knn=knn,
                _source=["metadata"],
                size=top_k,
            )
            hits = (resp.get("hits") or {}).get("hits") or []
            return [
                {
                    "id": str(h.get("_id", "")),
                    "score": float(h.get("_score", 0.0)),
                    "metadata": (h.get("_source") or {}).get("metadata", {}),
                }
                for h in hits
            ]
        except Exception as e:
            log.debug(f"ES kNN search failed: {e}")
            return []

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        if not ids:
            return
        try:
            for doc_id in ids:
                await self._client.delete(
                    index=self.index_name, id=str(doc_id), ignore=[404],
                )
        except Exception as e:
            log.debug(f"ES delete failed: {e}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# -------------------- Qdrant --------------------

class QdrantStore(VectorStore):
    """Qdrant vector store using qdrant-client AsyncQdrantClient.

    Requires: ``pip install qdrant-client``.

    Args:
        collection: Qdrant collection name. Must already exist unless
            ``create_collection=True`` is passed and ``dim`` is provided.
        url: Qdrant URL, e.g. ``http://localhost:6333``.
        api_key: optional cloud/API key.
        dim: vector dimension for auto-create.
        create_collection: create the collection if it is missing.
    """

    def __init__(
        self,
        collection: str,
        *,
        url: str | None = None,
        api_key: str | None = None,
        dim: int | None = None,
        create_collection: bool = False,
        distance: str = "Cosine",
    ):
        self.collection = collection
        self.url = url or os.environ.get("LARGESTACK_QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.environ.get("QDRANT_API_KEY")
        self.dim = dim
        self.create_collection = create_collection
        self.distance = distance
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.http import models as qmodels
        except ImportError as e:
            raise ImportError("QdrantStore needs: pip install 'qdrant-client'") from e
        if self.url == ":memory:" or self.url.startswith("file:"):
            location = ":memory:" if self.url == ":memory:" else self.url.removeprefix("file:")
            self._client = AsyncQdrantClient(location=location, api_key=self.api_key)
        else:
            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key)
        if self.create_collection:
            if not self.dim:
                raise ValueError("QdrantStore dim is required when create_collection=True")
            existing = await self._client.collection_exists(self.collection)
            if not existing:
                dist = getattr(qmodels.Distance, self.distance.upper(), qmodels.Distance.COSINE)
                await self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=qmodels.VectorParams(size=self.dim, distance=dist),
                )

    async def upsert(self, vectors: list[dict]) -> None:
        await self._connect()
        from qdrant_client.http import models as qmodels
        points = [
            qmodels.PointStruct(
                id=v["id"],
                vector=v["vector"],
                payload=v.get("metadata", {}),
            )
            for v in vectors
        ]
        await self._client.upsert(collection_name=self.collection, points=points)

    async def query(self, vector: list[float], top_k: int = 5, filter: dict | None = None) -> list[dict]:
        await self._connect()
        q_filter = None
        if filter:
            from qdrant_client.http import models as qmodels
            q_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v))
                    for k, v in filter.items()
                ]
            )
        if hasattr(self._client, "query_points"):
            response = await self._client.query_points(
                collection_name=self.collection,
                query=vector,
                query_filter=q_filter,
                limit=top_k,
                with_payload=True,
            )
            hits = response.points
        else:
            hits = await self._client.search(
                collection_name=self.collection,
                query_vector=vector,
                query_filter=q_filter,
                limit=top_k,
                with_payload=True,
            )
        return [
            {"id": str(h.id), "score": float(h.score), "metadata": dict(h.payload or {})}
            for h in hits
        ]

    async def delete(self, ids: list[str]) -> None:
        await self._connect()
        from qdrant_client.http import models as qmodels
        await self._client.delete(
            collection_name=self.collection,
            points_selector=qmodels.PointIdsList(points=list(ids)),
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
