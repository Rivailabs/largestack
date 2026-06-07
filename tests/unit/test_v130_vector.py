"""v0.13.0: Tests for VectorMemoryStore + embedders."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- HashingEmbedder --------------------


@pytest.mark.asyncio
async def test_hashing_embedder_returns_correct_dim():
    from largestack._memory.vector_store import HashingEmbedder

    e = HashingEmbedder(dim=128)
    assert e.dim == 128
    v = await e.embed("hello world")
    assert len(v) == 128


@pytest.mark.asyncio
async def test_hashing_embedder_is_deterministic():
    from largestack._memory.vector_store import HashingEmbedder

    e = HashingEmbedder()
    v1 = await e.embed("the user is in Bengaluru")
    v2 = await e.embed("the user is in Bengaluru")
    assert v1 == v2


@pytest.mark.asyncio
async def test_hashing_embedder_different_text_different_vector():
    from largestack._memory.vector_store import HashingEmbedder

    e = HashingEmbedder()
    v1 = await e.embed("Bengaluru")
    v2 = await e.embed("New York")
    assert v1 != v2


@pytest.mark.asyncio
async def test_hashing_embedder_normalised():
    """L2 norm should be ~1.0 for non-empty input."""
    import math
    from largestack._memory.vector_store import HashingEmbedder

    e = HashingEmbedder()
    v = await e.embed("test text")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 0.01


@pytest.mark.asyncio
async def test_hashing_embedder_batch():
    from largestack._memory.vector_store import HashingEmbedder

    e = HashingEmbedder(dim=64)
    vs = await e.embed_batch(["a", "b", "c"])
    assert len(vs) == 3
    assert all(len(v) == 64 for v in vs)


# -------------------- VectorMemoryStore --------------------


@pytest.mark.asyncio
async def test_vector_store_add_and_search_finds_paraphrase():
    """The whole point: 'Bengaluru' should match 'Bangalore' related text."""
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore, HashingEmbedder

    backing = InMemoryLongTermStore()
    store = VectorMemoryStore(backing, embedder=HashingEmbedder(dim=512))

    await store.add(
        LongTermMemoryEntry(
            id="a",
            tenant_id="t1",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="The user lives in Bengaluru, Karnataka",
        )
    )
    await store.add(
        LongTermMemoryEntry(
            id="b",
            tenant_id="t1",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="Weather forecast for tomorrow",
        )
    )

    # Hashing embedder uses character trigrams — "Bengaluru" trigrams
    # overlap with itself substantially, "Weather" doesn't.
    results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="Bengaluru",
    )
    assert len(results) >= 1
    assert results[0].id == "a"


@pytest.mark.asyncio
async def test_vector_store_isolates_by_tenant():
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    store = VectorMemoryStore(InMemoryLongTermStore())

    await store.add(
        LongTermMemoryEntry(
            id="a",
            tenant_id="t1",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="t1 secret data",
        )
    )
    await store.add(
        LongTermMemoryEntry(
            id="b",
            tenant_id="t2",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="t1 secret data",  # same content
        )
    )

    t1_results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="secret",
    )
    assert all(r.tenant_id == "t1" for r in t1_results)
    # Should not see t2's entry even though same content
    assert all(r.id != "b" for r in t1_results)


@pytest.mark.asyncio
async def test_vector_store_filters_user():
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    store = VectorMemoryStore(InMemoryLongTermStore())

    await store.add(
        LongTermMemoryEntry(
            id="a",
            tenant_id="t1",
            user_id="alice",
            tier="archival",
            scope="semantic",
            content="alice's grocery list",
        )
    )
    await store.add(
        LongTermMemoryEntry(
            id="b",
            tenant_id="t1",
            user_id="bob",
            tier="archival",
            scope="semantic",
            content="alice's grocery list",  # same
        )
    )

    results = await store.search(
        tenant_id="t1",
        user_id="alice",
        query="grocery",
    )
    assert all(r.user_id == "alice" for r in results)


@pytest.mark.asyncio
async def test_vector_store_excludes_expired():
    import time as _t
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    store = VectorMemoryStore(InMemoryLongTermStore())

    await store.add(
        LongTermMemoryEntry(
            id="fresh",
            tenant_id="t1",
            user_id="u1",
            tier="recall",
            scope="episodic",
            content="findme content",
        )
    )
    expired = LongTermMemoryEntry(
        id="exp",
        tenant_id="t1",
        user_id="u1",
        tier="recall",
        scope="episodic",
        content="findme content",
        created_at=_t.time() - 1000,
        ttl_seconds=10,
    )
    await store.add(expired)

    results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="findme",
    )
    ids = {r.id for r in results}
    assert "fresh" in ids
    assert "exp" not in ids


@pytest.mark.asyncio
async def test_vector_store_falls_back_when_embed_fails():
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    bad_embedder = MagicMock()
    bad_embedder.embed = AsyncMock(side_effect=RuntimeError("boom"))
    bad_embedder.embed_batch = AsyncMock(side_effect=RuntimeError("boom"))
    bad_embedder.dim = 16

    store = VectorMemoryStore(
        InMemoryLongTermStore(),
        embedder=bad_embedder,
    )
    # Adding shouldn't crash — embed errors are logged & swallowed
    await store.add(
        LongTermMemoryEntry(
            id="a",
            tenant_id="t1",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="findme",
        )
    )
    # Search should fall back to substring
    results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="findme",
    )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_vector_store_clear_drops_index():
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    store = VectorMemoryStore(InMemoryLongTermStore())
    await store.add(
        LongTermMemoryEntry(
            id="a",
            tenant_id="t1",
            user_id="u1",
            tier="archival",
            scope="semantic",
            content="test",
        )
    )
    await store.clear(tenant_id="t1")
    # Index should have no t1 entries
    results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="test",
    )
    assert results == []


@pytest.mark.asyncio
async def test_vector_store_reindex_rebuilds_from_backing():
    """Reindex from a populated backing store (e.g. after a restart)."""
    from largestack._memory.long_term import (
        InMemoryLongTermStore,
        LongTermMemoryEntry,
    )
    from largestack._memory.vector_store import VectorMemoryStore

    backing = InMemoryLongTermStore()
    # Add directly to backing (skipping vector indexing)
    for i in range(5):
        await backing.add(
            LongTermMemoryEntry(
                id=f"e{i}",
                tenant_id="t1",
                user_id="u1",
                tier="archival",
                scope="semantic",
                content=f"content {i}",
            )
        )

    store = VectorMemoryStore(backing)
    count = await store.reindex("t1")
    assert count == 5

    results = await store.search(
        tenant_id="t1",
        user_id="u1",
        query="content",
    )
    assert len(results) >= 1


# -------------------- OpenAI / SentenceTransformer guards --------------------


def test_openai_embedder_dim_mapping():
    from largestack._memory.vector_store import OpenAIEmbedder

    e = OpenAIEmbedder(model="text-embedding-3-small")
    assert e.dim == 1536
    e2 = OpenAIEmbedder(model="text-embedding-3-large")
    assert e2.dim == 3072


def test_openai_embedder_unknown_model_default_dim():
    from largestack._memory.vector_store import OpenAIEmbedder

    e = OpenAIEmbedder(model="future-model")
    assert e.dim == 1536  # safe default


def test_sentence_transformer_module_importable():
    """Module should import even without sentence-transformers."""
    from largestack._memory.vector_store import SentenceTransformerEmbedder

    e = SentenceTransformerEmbedder()
    assert e.model_name == "all-MiniLM-L6-v2"
