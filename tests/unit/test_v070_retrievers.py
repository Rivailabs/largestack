"""v0.7.0: Advanced retriever tests (multi-query, HyDE, RRF)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- RRF (pure function — most tests here) --------------------


def test_rrf_single_list_preserves_order():
    """With one list, RRF scores match input order (rank 1 > rank 2 > ...)."""
    from largestack._retrievers import rrf_fuse

    docs = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    out = rrf_fuse([docs], k=3)
    assert [d["id"] for d in out] == ["a", "b", "c"]
    assert out[0]["rrf_score"] > out[1]["rrf_score"] > out[2]["rrf_score"]


def test_rrf_combines_multiple_lists_correctly():
    """Doc that appears high in both lists scores highest."""
    from largestack._retrievers import rrf_fuse

    list1 = [{"id": "x"}, {"id": "y"}, {"id": "z"}]
    list2 = [{"id": "y"}, {"id": "x"}, {"id": "w"}]
    out = rrf_fuse([list1, list2], k=4)
    ids = [d["id"] for d in out]
    # x appears at rank 1 + 2 = high
    # y appears at rank 2 + 1 = high (similar to x)
    # z appears at rank 3 only
    # w appears at rank 3 only
    assert set(ids[:2]) == {"x", "y"}  # top 2 are x and y
    assert "z" in ids
    assert "w" in ids


def test_rrf_uses_60_as_canonical_k():
    """Verifies the score formula uses rrf_k=60 (the standard)."""
    from largestack._retrievers import rrf_fuse

    list1 = [{"id": "a"}]
    out = rrf_fuse([list1], k=1)
    expected = 1.0 / (60 + 1)  # rank 1, rrf_k=60
    assert abs(out[0]["rrf_score"] - expected) < 1e-6


def test_rrf_drops_docs_without_id_field():
    from largestack._retrievers import rrf_fuse

    list1 = [{"id": "a"}, {"no_id": "x"}, {"id": "b"}]
    out = rrf_fuse([list1], k=10)
    assert len(out) == 2
    assert {d["id"] for d in out} == {"a", "b"}


def test_rrf_handles_empty_lists():
    from largestack._retrievers import rrf_fuse

    assert rrf_fuse([], k=5) == []
    assert rrf_fuse([[], [], []], k=5) == []


def test_rrf_custom_id_field():
    from largestack._retrievers import rrf_fuse

    docs = [{"doc_id": "a"}, {"doc_id": "b"}]
    out = rrf_fuse([docs], k=2, id_field="doc_id")
    assert [d["doc_id"] for d in out] == ["a", "b"]


def test_rrf_caps_at_k():
    from largestack._retrievers import rrf_fuse

    docs = [{"id": str(i)} for i in range(20)]
    out = rrf_fuse([docs], k=5)
    assert len(out) == 5


def test_rrf_validates_inputs():
    from largestack._retrievers import rrf_fuse

    with pytest.raises(ValueError, match="k must be"):
        rrf_fuse([[{"id": "a"}]], k=0)
    with pytest.raises(ValueError, match="rrf_k must be"):
        rrf_fuse([[{"id": "a"}]], k=1, rrf_k=0)


def test_rrf_score_decreases_with_rank():
    """A doc at rank 1 must score higher than the same doc at rank 5."""
    from largestack._retrievers import rrf_fuse

    list_high = [{"id": "x"}]  # rank 1
    list_low = [{"id": "filler"}, {"id": "f2"}, {"id": "f3"}, {"id": "f4"}, {"id": "x"}]  # rank 5

    out_high = rrf_fuse([list_high], k=1)
    out_low = rrf_fuse([list_low], k=10)
    x_low = next(d for d in out_low if d["id"] == "x")
    assert out_high[0]["rrf_score"] > x_low["rrf_score"]


# -------------------- Multi-Query --------------------


@pytest.mark.asyncio
async def test_multi_query_generates_variants_and_fuses():
    """End-to-end: agent generates variants, each query retrieves, RRF fuses."""
    from largestack._retrievers import multi_query_retrieve

    fake_agent_result = MagicMock()
    fake_agent_result.content = "rate limiting setup\nrate limit configuration\nthrottling config"
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_agent_result)

    # Each query returns slightly different docs
    async def retriever(q: str, k: int) -> list[dict]:
        if "limiting" in q:
            return [{"id": "doc1"}, {"id": "doc2"}]
        if "configuration" in q:
            return [{"id": "doc2"}, {"id": "doc3"}]
        if "throttling" in q:
            return [{"id": "doc3"}, {"id": "doc4"}]
        return [{"id": "doc1"}]

    out = await multi_query_retrieve(
        query="how to configure rate limits",
        agent=agent,
        retriever=retriever,
        n_variants=3,
        k=4,
    )

    assert len(out) <= 4
    ids = {d["id"] for d in out}
    # Expected coverage
    assert "doc2" in ids  # appears in 2 lists → high score
    assert "doc1" in ids or "doc3" in ids


@pytest.mark.asyncio
async def test_multi_query_handles_agent_failure_gracefully():
    """If the variant-generating agent fails, still try the original query."""
    from largestack._retrievers import multi_query_retrieve

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))

    async def retriever(q: str, k: int) -> list[dict]:
        return [{"id": "fallback_doc"}]

    out = await multi_query_retrieve(
        query="what is X",
        agent=agent,
        retriever=retriever,
        n_variants=3,
        k=5,
    )
    # Should still get the original-query results
    assert len(out) == 1
    assert out[0]["id"] == "fallback_doc"


@pytest.mark.asyncio
async def test_multi_query_validates_inputs():
    from largestack._retrievers import multi_query_retrieve

    agent = MagicMock()
    agent.run = AsyncMock()

    async def r(q, k):
        return []

    with pytest.raises(ValueError):
        await multi_query_retrieve("q", agent, r, n_variants=0)
    with pytest.raises(ValueError):
        await multi_query_retrieve("q", agent, r, k=0)


# -------------------- HyDE --------------------


@pytest.mark.asyncio
async def test_hyde_generates_then_embeds_then_searches():
    """HyDE flow: LLM answer → embed answer → vector search."""
    from largestack._retrievers import hyde_retrieve

    fake_result = MagicMock()
    fake_result.content = "TLS handshake involves a ClientHello followed by ServerHello..."
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    embedder = AsyncMock(return_value=[0.1] * 1536)

    vstore = MagicMock()
    vstore.query = AsyncMock(
        return_value=[
            {"id": "tls_rfc", "score": 0.95},
            {"id": "tls_blog", "score": 0.80},
        ]
    )

    out = await hyde_retrieve(
        query="explain TLS handshake",
        agent=agent,
        embedder=embedder,
        vector_store=vstore,
        k=5,
    )

    # Embedder was called with the hypothetical answer, not the query
    embed_call_arg = embedder.await_args.args[0]
    assert "ClientHello" in embed_call_arg
    assert "explain" not in embed_call_arg.lower() or "TLS" in embed_call_arg

    assert len(out) == 2
    assert out[0]["id"] == "tls_rfc"


@pytest.mark.asyncio
async def test_hyde_falls_back_to_query_when_llm_fails():
    """If LLM can't produce a hypothetical answer, embed the query itself."""
    from largestack._retrievers import hyde_retrieve

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("LLM dead"))
    embedder = AsyncMock(return_value=[0.0] * 1536)
    vstore = MagicMock()
    vstore.query = AsyncMock(return_value=[{"id": "x"}])

    out = await hyde_retrieve(
        query="some query",
        agent=agent,
        embedder=embedder,
        vector_store=vstore,
        k=3,
    )
    assert embedder.await_args.args[0] == "some query"
    assert out == [{"id": "x"}]


@pytest.mark.asyncio
async def test_hyde_returns_empty_when_embedding_fails():
    from largestack._retrievers import hyde_retrieve

    fake_result = MagicMock()
    fake_result.content = "hypothesis"
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    embedder = AsyncMock(side_effect=RuntimeError("embed API down"))
    vstore = MagicMock()
    vstore.query = AsyncMock()

    out = await hyde_retrieve(query="q", agent=agent, embedder=embedder, vector_store=vstore, k=3)
    assert out == []
    vstore.query.assert_not_called()


@pytest.mark.asyncio
async def test_hyde_validates_k():
    from largestack._retrievers import hyde_retrieve

    with pytest.raises(ValueError):
        await hyde_retrieve(
            query="q",
            agent=MagicMock(),
            embedder=AsyncMock(),
            vector_store=MagicMock(),
            k=0,
        )
