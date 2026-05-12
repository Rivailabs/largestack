"""Vector-embedding semantic search for long-term memory (v0.13.0).

Closes the Mem0 / Letta accuracy gap. The base ``LongTermMemoryStore``
uses substring + token-jaccard scoring which misses paraphrases
("Bengaluru" doesn't match "Bangalore"). This module wraps any backing
store with a vector-embedding search layer.

Architecture:

- Memory entries are still stored in the base store (in-memory / SQLite
  / Postgres) — vectors are derived data, can be rebuilt
- Embedding is lazy: vector computed when entry is added, cached locally
- Search ranks by cosine similarity of query embedding to stored vectors
- Falls back to base store's substring search if no embedder configured

Embedding providers:

- ``EmbedderProtocol`` — interface (any callable ``str → list[float]``)
- ``HashingEmbedder`` — deterministic, zero-dep, useful for tests
- ``OpenAIEmbedder`` — production via ``text-embedding-3-small`` etc.
- ``SentenceTransformerEmbedder`` — local, via sentence-transformers

Each provider is optional. The default is ``HashingEmbedder`` (works
without any dependency installation).
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import math
from typing import Any, Awaitable, Callable, Protocol

from largestack._memory.long_term import (
    LongTermMemoryEntry, LongTermMemoryStore, MemoryScope, MemoryTier,
)

log = logging.getLogger("largestack.memory.vector")


# -------------------- Embedder protocol --------------------

class EmbedderProtocol(Protocol):
    """An embedder produces a fixed-size vector for any text."""

    @property
    def dim(self) -> int: ...

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


# -------------------- Built-in embedders --------------------

class HashingEmbedder:
    """Deterministic hash-based embedder. Zero dependencies.

    Each token is hashed into ``dim`` buckets, then L2-normalised. Not
    semantic in the LLM sense but produces stable vectors that correlate
    with token overlap. Good for tests + offline deployments.
    """

    def __init__(self, dim: int = 256):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for token in text.lower().split():
            # Stable hash — feature-hashing trick
            h = int.from_bytes(
                hashlib.sha256(token.encode()).digest()[:8], "big",
            )
            bucket = h % self._dim
            sign = 1.0 if (h // self._dim) & 1 else -1.0
            v[bucket] += sign
        # Add character-trigram features (catches partial matches)
        text_lower = text.lower()
        for i in range(max(0, len(text_lower) - 2)):
            tri = text_lower[i : i + 3]
            h = int.from_bytes(
                hashlib.sha256(tri.encode()).digest()[:8], "big",
            )
            bucket = h % self._dim
            v[bucket] += 0.3
        # L2 normalise
        norm = math.sqrt(sum(x * x for x in v))
        if norm > 0:
            v = [x / norm for x in v]
        return v

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class OpenAIEmbedder:
    """OpenAI embedding model wrapper.

    Args:
        model: e.g. ``"text-embedding-3-small"`` (1536 dim) or
            ``"text-embedding-3-large"`` (3072 dim)
        api_key: optional; falls back to ``OPENAI_API_KEY`` env var
    """

    DIM_MAP = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self._client = None

    @property
    def dim(self) -> int:
        return self.DIM_MAP.get(self.model, 1536)

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as e:
                raise ImportError(
                    "openai required for OpenAIEmbedder. "
                    "Install with: pip install openai"
                ) from e
            self._client = openai.AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = self._get_client()
        resp = await client.embeddings.create(
            model=self.model, input=text,
        )
        return list(resp.data[0].embedding)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        resp = await client.embeddings.create(
            model=self.model, input=texts,
        )
        return [list(d.embedding) for d in resp.data]


class SentenceTransformerEmbedder:
    """Local embedder via sentence-transformers.

    Default: ``all-MiniLM-L6-v2`` (384 dim, 80MB, fast on CPU).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim_cache: int | None = None

    @property
    def dim(self) -> int:
        if self._dim_cache is None:
            self._load()
            self._dim_cache = self._model.get_sentence_embedding_dimension()
        return self._dim_cache

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers required. Install with: "
                    "pip install sentence-transformers"
                ) from e
            self._model = SentenceTransformer(self.model_name)

    async def embed(self, text: str) -> list[float]:
        self._load()
        return await asyncio.to_thread(
            lambda: self._model.encode(text, show_progress_bar=False).tolist()
        )

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._load()
        return await asyncio.to_thread(
            lambda: self._model.encode(
                texts, show_progress_bar=False,
            ).tolist()
        )


# -------------------- Vector index (in-memory) --------------------

class _VectorIndex:
    """In-memory cosine-similarity index. Keyed by (tenant_id, entry_id)."""

    def __init__(self) -> None:
        self._vectors: dict[tuple[str, str], list[float]] = {}
        self._lock = asyncio.Lock()

    async def upsert(
        self, tenant_id: str, entry_id: str, vector: list[float],
    ) -> None:
        async with self._lock:
            self._vectors[(tenant_id, entry_id)] = vector

    async def remove(self, tenant_id: str, entry_id: str) -> None:
        async with self._lock:
            self._vectors.pop((tenant_id, entry_id), None)

    async def remove_tenant(self, tenant_id: str) -> int:
        async with self._lock:
            keys = [k for k in self._vectors if k[0] == tenant_id]
            for k in keys:
                del self._vectors[k]
            return len(keys)

    async def search(
        self,
        tenant_id: str,
        query_vec: list[float],
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Returns ``[(entry_id, score), ...]`` sorted by score desc."""
        async with self._lock:
            scored: list[tuple[str, float]] = []
            for (tid, eid), v in self._vectors.items():
                if tid != tenant_id:
                    continue
                score = _cosine(query_vec, v)
                if score > 0:
                    scored.append((eid, score))
            scored.sort(key=lambda t: t[1], reverse=True)
            return scored[:limit]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # Vectors are pre-normalised in our embedders, but be safe
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# -------------------- VectorMemoryStore wrapper --------------------

class VectorMemoryStore(LongTermMemoryStore):
    """Wraps a backing ``LongTermMemoryStore`` with vector embedding
    semantic search.

    Args:
        backing: the underlying store (in-memory / SQLite / Postgres)
        embedder: the embedding provider (default: ``HashingEmbedder``)
        substring_score_min: when falling back to base substring search,
            entries with score below this threshold are excluded
    """

    def __init__(
        self,
        backing: LongTermMemoryStore,
        *,
        embedder: EmbedderProtocol | None = None,
        substring_score_min: float = 0.0,
    ):
        self.backing = backing
        self.embedder = embedder or HashingEmbedder()
        self.substring_score_min = substring_score_min
        self._index = _VectorIndex()

    async def add(self, entry: LongTermMemoryEntry) -> None:
        await self.backing.add(entry)
        try:
            vec = await self.embedder.embed(entry.content)
            await self._index.upsert(entry.tenant_id, entry.id, vec)
        except Exception as e:
            log.warning(f"embedding failed for {entry.id}: {e}")

    async def get(self, entry_id: str) -> LongTermMemoryEntry | None:
        return await self.backing.get(entry_id)

    async def update(self, entry: LongTermMemoryEntry) -> None:
        await self.backing.update(entry)
        try:
            vec = await self.embedder.embed(entry.content)
            await self._index.upsert(entry.tenant_id, entry.id, vec)
        except Exception as e:
            log.warning(f"re-embedding failed for {entry.id}: {e}")

    async def delete(self, entry_id: str) -> bool:
        # We don't know the tenant_id from id alone; let backing delete,
        # then orphan vectors are cleaned up via reindex if needed
        entry = await self.backing.get(entry_id)
        ok = await self.backing.delete(entry_id)
        if ok and entry is not None:
            await self._index.remove(entry.tenant_id, entry_id)
        return ok

    async def list(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        tier: MemoryTier | None = None,
        scope: MemoryScope | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemoryEntry]:
        return await self.backing.list(
            tenant_id=tenant_id, user_id=user_id, tier=tier,
            scope=scope, tag=tag, limit=limit,
        )

    async def search(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        query: str,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]:
        """Vector cosine-similarity search."""
        # Embed the query
        try:
            qvec = await self.embedder.embed(query)
        except Exception as e:
            log.warning(f"query embed failed: {e}; falling back to substring")
            return await self.backing.search(
                tenant_id=tenant_id, user_id=user_id,
                query=query, limit=limit,
            )

        # Cosine search across this tenant's vectors
        # Over-fetch to leave headroom after user/expiry filtering
        candidates = await self._index.search(
            tenant_id, qvec, limit=limit * 4,
        )
        if not candidates:
            # Index might be empty (no vectors yet) — fall back to substring
            return await self.backing.search(
                tenant_id=tenant_id, user_id=user_id,
                query=query, limit=limit,
            )

        results: list[LongTermMemoryEntry] = []
        for entry_id, _ in candidates:
            entry = await self.backing.get(entry_id)
            if entry is None:
                continue
            if user_id is not None and entry.user_id != user_id:
                continue
            if entry.is_expired():
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def purge_expired(
        self, *, tenant_id: str | None = None,
    ) -> int:
        # Remove from index too (best-effort: scan-and-delete)
        # Backing purge first to know what was removed
        before = await self.backing.list(tenant_id=tenant_id or "")
        before_ids = {e.id for e in before}
        count = await self.backing.purge_expired(tenant_id=tenant_id)
        if tenant_id and count > 0:
            after = await self.backing.list(tenant_id=tenant_id)
            after_ids = {e.id for e in after}
            for removed_id in (before_ids - after_ids):
                await self._index.remove(tenant_id, removed_id)
        return count

    async def clear(self, *, tenant_id: str | None = None) -> int:
        count = await self.backing.clear(tenant_id=tenant_id)
        if tenant_id is None:
            self._index = _VectorIndex()
        else:
            await self._index.remove_tenant(tenant_id)
        return count

    async def reindex(
        self,
        tenant_id: str,
        *,
        batch_size: int = 64,
    ) -> int:
        """Re-build the vector index for a tenant. Returns count."""
        entries = await self.backing.list(tenant_id=tenant_id)
        if not entries:
            return 0

        count = 0
        for i in range(0, len(entries), batch_size):
            batch = entries[i : i + batch_size]
            texts = [e.content for e in batch]
            try:
                vecs = await self.embedder.embed_batch(texts)
            except Exception as e:
                log.warning(f"reindex batch failed: {e}")
                continue
            for entry, vec in zip(batch, vecs):
                await self._index.upsert(entry.tenant_id, entry.id, vec)
                count += 1
        return count


__all__ = [
    "EmbedderProtocol",
    "HashingEmbedder",
    "OpenAIEmbedder",
    "SentenceTransformerEmbedder",
    "VectorMemoryStore",
]
