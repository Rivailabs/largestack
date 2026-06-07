# RAG

`create_rag(documents, top_k=, dense=, embed_fn=, reranker=)` builds a retrieval
pipeline. By default it uses **BM25 keyword search** (Okapi BM25 + a conservative
suffix stemmer so `refunds`/`refund` match) — instant, offline, no extra deps.
Dense vector search and reranking are opt-in.

```python
from largestack.rag import create_rag

docs = [
    "Refunds are available within 30 days of purchase.",
    "Our warranty covers manufacturing defects for 12 months.",
    "Shipping is free for orders over fifty dollars.",
]
rag = create_rag(docs, top_k=2)
hits = rag.retrieve("how long is the refund window?")
for h in hits:
    print(round(h["score"], 3), h["text"])
```

`retrieve()` returns a list of `{"text", "score", "index"}` dicts (when a reranker
is set, a `"rerank_score"` is added too).

## `create_rag` arguments

| Arg | Default | Notes |
|---|---|---|
| `documents` | `None` | corpus to chunk + index (call `.ingest(docs)` later to add) |
| `chunk_size` | `512` | recursive chunker target size (chars) |
| `top_k` | `5` | results returned by `retrieve()` / used by `build_context()` |
| `dense` | `False` | `True` (or `"auto"`) enables hybrid BM25 + dense via a local `sentence-transformers` model (`all-MiniLM-L6-v2`). No-op fallback to BM25 if the package isn't installed |
| `embed_fn` | `None` | your own **sync** `str -> list[float]` embedder; enables hybrid retrieval without `sentence-transformers` |
| `reranker` | `None` | a `Reranker` (see below) to re-score candidates after retrieval |

Hybrid retrieval fuses BM25 and dense rankings with Reciprocal Rank Fusion (RRF).
Dense is opt-in: `pip install largestack[rag]` for `sentence-transformers`, or pass
your own `embed_fn`.

## Methods

| Method | Returns | Notes |
|---|---|---|
| `retrieve(query, top_k=None)` | `list[dict]` | `{"text", "score", "index"}` (+`"rerank_score"` if reranking) |
| `build_context(query, top_k=None)` | `str` | retrieved chunks joined as `[Source 1] ... [Source 2] ...` |
| `as_tool()` | `@tool` | a `search_knowledge(query)` tool you can hand to an `Agent` |
| `ingest(documents)` | — | chunk + (re)index more documents |

```python
print(rag.build_context("refund window"))
# [Source 1] Refunds are available within 30 days of purchase.

tool = rag.as_tool()        # name: "search_knowledge" — pass to Agent(tools=[tool])
```

## Reranking (opt-in)

Pass a `Reranker` to re-score retrieved candidates for precision. The default
`keyword` mode (TF-IDF + n-gram overlap) needs no extra deps; other modes are opt-in.

```python
from largestack.rag import create_rag
from largestack._rag.reranker import Reranker

rag = create_rag(docs, top_k=2, reranker=Reranker(mode="keyword"))
hits = rag.retrieve("refund window")   # each hit now has a "rerank_score"
```

| `mode` | Backend | Deps / auth |
|---|---|---|
| `"keyword"` | TF-IDF + n-gram overlap | none (default) |
| `"cross_encoder"` | local `BAAI/bge-reranker-v2-m3` | `sentence-transformers` |
| `"cohere"` | Cohere Rerank API | `COHERE_API_KEY` (or `LARGESTACK_COHERE_API_KEY`) |
| `"voyage"` | Voyage AI Rerank API | `VOYAGE_API_KEY` (or `LARGESTACK_VOYAGE_API_KEY`) |
| `"custom"` | your `custom_fn(query, docs)` | none |

API/model modes fall back to `keyword` if the key/package is missing.

## Citations

For per-sentence citation mapping against trusted sources, use the secure pipeline,
which returns grounded answers with `citations`/`sources`. See
[Secure RAG agent](guides/secure_rag.md).

## Vector-store backends

`largestack._vectorstores` ships 18 adapters that all implement the same async
`VectorStore` interface (`upsert` / `query(vector, top_k, filter)` / `delete` /
`close`), so they're interchangeable. They are **not auto-wired into `create_rag`** —
`create_rag` retrieves over in-memory chunks (BM25, + dense embeddings when enabled).
Wire a store in your own code (e.g. embed chunks, `upsert`, then `query` per request).

| Store | Backend | Install / requires |
|---|---|---|
| `PineconeStore` | Pinecone (asyncio) | `pip install pinecone[asyncio]`; `PINECONE_API_KEY` |
| `WeaviateStore` | Weaviate v4 | `pip install weaviate-client>=4.7` |
| `PgVectorStore` | Postgres + pgvector | `pip install asyncpg`; pgvector extension |
| `MilvusStore` | Milvus | `pip install pymilvus>=2.4` |
| `RedisVectorStore` | Redis Stack / RediSearch | `pip install redis>=5.0` |
| `ElasticsearchStore` | Elasticsearch | `pip install 'elasticsearch[async]>=8.0'` |
| `ElasticsearchDenseVectorStore` | ES native `dense_vector` + kNN | `pip install 'elasticsearch[async]>=8.0'` |
| `OpenSearchStore` | OpenSearch | `pip install 'opensearch-py>=2.4'` |
| `MongoDBAtlasStore` | MongoDB Atlas | `pip install motor>=3.5` |
| `MongoAtlasVectorStore` | MongoDB Atlas Vector Search | `pip install motor>=3.5` |
| `ChromaStore` | Chroma | `pip install chromadb>=0.5` |
| `LanceDBStore` | LanceDB | `pip install lancedb>=0.13` |
| `AzureCognitiveSearchStore` | Azure AI Search | `pip install azure-search-documents>=11.4` |
| `QdrantStore` | Qdrant (asyncio) | `pip install qdrant-client`; `QDRANT_API_KEY` (cloud) |
| `FaissPersistentStore` | FAISS with disk persistence | `pip install faiss-cpu` |
| `DuckDBVectorStore` | DuckDB + `vss` | `pip install duckdb>=0.10` |
| `SupabaseVectorStore` | Supabase (pgvector wrapper) | `pip install asyncpg` |
| `AuroraPgVectorStore` | AWS Aurora Postgres + pgvector | `pip install asyncpg` |

```python
from largestack._vectorstores import QdrantStore

async def example():
    store = QdrantStore(collection="docs", url="http://localhost:6333")
    await store.upsert([{"id": "1", "vector": [0.1, 0.2], "metadata": {"src": "faq"}}])
    results = await store.query(vector=[0.1, 0.2], top_k=5)
    await store.close()
```

Each adapter reports cleanly if its underlying SDK isn't installed, so importing
`largestack._vectorstores` never fails at startup even with no DB clients present.

## Maturity Boundaries

Do not market RAG as fully enterprise-hardened until these gates have fresh
release evidence:

| Area | Current public claim | Required hardening proof |
|---|---|---|
| Retrieval | Local retrieval works with evaluation coverage | Production-scale corpus benchmark with latency and recall targets |
| Reranking | Rerank path exists | Non-regression benchmark across representative corpora |
| Citation confidence | Citation presence is tested | Confidence calibration against labeled answer/citation pairs |
| Tenant filtering | Tenant-aware paths exist | Cross-tenant leakage tests for every persistent vector backend |
| Metadata indices | Metadata filters are supported in selected paths | Backend-specific index/filter validation at scale |
| GraphRAG | Experimental/conceptual | Real graph construction, query tests, and failure-mode docs |
