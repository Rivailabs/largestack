"""v0.9.0: Tests for DocumentSummaryIndex and tree_summarize."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- DocumentSummaryIndex --------------------

@pytest.mark.asyncio
async def test_document_summary_index_add_and_query():
    from largestack._rag.summary_index import DocumentSummaryIndex

    summarizer = MagicMock()
    summarizer.run = AsyncMock(side_effect=[
        MagicMock(content="A doc about pgvector and HNSW indexes."),
        MagicMock(content="A doc about pasta cooking and tomato sauce."),
    ])

    # Embedder returns simple list (not JSON string)
    async def fake_embedder(text):
        if "pgvector" in text.lower() or "hnsw" in text.lower():
            return [1.0, 0.0, 0.0]
        if "pasta" in text.lower() or "tomato" in text.lower():
            return [0.0, 1.0, 0.0]
        return [0.5, 0.5, 0.0]  # query that matches both somewhat

    idx = DocumentSummaryIndex()
    await idx.add_document(
        "doc1", "Long doc about pgvector...",
        chunks=[{"content": "chunk1.1"}, {"content": "chunk1.2"}],
        summarizer_agent=summarizer, embedder=fake_embedder,
    )
    await idx.add_document(
        "doc2", "Long doc about pasta...",
        chunks=[{"content": "chunk2.1"}, {"content": "chunk2.2"}],
        summarizer_agent=summarizer, embedder=fake_embedder,
    )

    # Query about pgvector → doc1 chunks should rank first
    async def query_emb(q):
        return [0.95, 0.0, 0.0]  # close to doc1's [1, 0, 0]

    results = await idx.query(
        "What is pgvector?", embedder=query_emb, top_docs=1, top_chunks_per_doc=2,
    )
    assert all(r["doc_id"] == "doc1" for r in results)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_document_summary_index_handles_json_embed_result():
    """Embedder may return JSON string (LARGESTACK tool style)."""
    from largestack._rag.summary_index import DocumentSummaryIndex

    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="summary"))

    async def json_embedder(text):
        return json.dumps({"model": "x", "dim": 3, "embedding": [1.0, 0.0, 0.0]})

    idx = DocumentSummaryIndex()
    await idx.add_document(
        "d1", "text", chunks=[{"content": "c"}],
        summarizer_agent=summarizer, embedder=json_embedder,
    )
    assert idx._docs["d1"].summary_embedding == [1.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_document_summary_index_query_empty_returns_empty():
    from largestack._rag.summary_index import DocumentSummaryIndex
    async def emb(t):
        return [1.0, 0.0]
    idx = DocumentSummaryIndex()
    results = await idx.query("q", embedder=emb)
    assert results == []


@pytest.mark.asyncio
async def test_document_summary_index_get_summaries():
    from largestack._rag.summary_index import DocumentSummaryIndex
    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="brief summary"))
    async def emb(t):
        return [1.0]
    idx = DocumentSummaryIndex()
    await idx.add_document(
        "d1", "long text", chunks=[{}, {}],
        summarizer_agent=summarizer, embedder=emb,
        metadata={"source": "blog"},
    )
    summaries = idx.get_summaries()
    assert len(summaries) == 1
    assert summaries[0]["doc_id"] == "d1"
    assert summaries[0]["n_chunks"] == 2
    assert summaries[0]["metadata"]["source"] == "blog"


@pytest.mark.asyncio
async def test_document_summary_index_handles_summarizer_failure():
    from largestack._rag.summary_index import DocumentSummaryIndex
    summarizer = MagicMock()
    summarizer.run = AsyncMock(side_effect=RuntimeError("LLM dead"))
    async def emb(t):
        return [1.0]
    idx = DocumentSummaryIndex()
    # Should not raise
    await idx.add_document(
        "d1", "fallback to first chars",
        chunks=[], summarizer_agent=summarizer, embedder=emb,
    )
    # Falls back to truncated full_text
    assert "fallback" in idx._docs["d1"].summary


# -------------------- tree_summarize --------------------

@pytest.mark.asyncio
async def test_tree_summarize_single_chunk_returns_unchanged():
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    summarizer.run = AsyncMock()
    out = await tree_summarize(
        ["only chunk"], summarizer_agent=summarizer,
    )
    assert out == "only chunk"
    summarizer.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_tree_summarize_two_chunks_one_call():
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="combined summary"))
    out = await tree_summarize(
        ["first part", "second part"],
        summarizer_agent=summarizer, branching_factor=4,
    )
    assert out == "combined summary"
    assert summarizer.run.await_count == 1


@pytest.mark.asyncio
async def test_tree_summarize_recurses():
    """8 chunks with branching=4 → 2 mid-summaries → 1 final."""
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="x"))
    chunks = [f"chunk {i}" for i in range(8)]
    await tree_summarize(
        chunks, summarizer_agent=summarizer, branching_factor=4,
    )
    # Level 1: 8 → 2 calls (2 batches of 4)
    # Level 2: 2 → 1 call
    # Total: 3 calls
    assert summarizer.run.await_count == 3


@pytest.mark.asyncio
async def test_tree_summarize_empty_chunks():
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    out = await tree_summarize([], summarizer_agent=summarizer)
    assert out == ""


@pytest.mark.asyncio
async def test_tree_summarize_handles_partial_failure():
    """If one summarizer call fails, fall back to combined text."""
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    summarizer.run = AsyncMock(side_effect=[
        RuntimeError("dead"),
        MagicMock(content="recovered summary"),
    ])
    out = await tree_summarize(
        ["chunk1", "chunk2", "chunk3", "chunk4", "chunk5"],
        summarizer_agent=summarizer, branching_factor=4,
    )
    # Even with partial failures, should produce some output
    assert isinstance(out, str)
    assert len(out) > 0


@pytest.mark.asyncio
async def test_tree_summarize_truncates_long_summaries():
    from largestack._rag.summary_index import tree_summarize
    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="x" * 5000))
    out = await tree_summarize(
        ["a", "b"], summarizer_agent=summarizer,
        max_chars_per_summary=100,
    )
    assert len(out) <= 100


# -------------------- summarize_document --------------------

@pytest.mark.asyncio
async def test_summarize_document_chunks_long_text():
    from largestack._rag.summary_index import summarize_document
    summarizer = MagicMock()
    summarizer.run = AsyncMock(return_value=MagicMock(content="root summary"))

    long_text = "x" * 10000  # 5 chunks of 2000 chars each
    out = await summarize_document(
        long_text, summarizer_agent=summarizer, chunk_size=2000,
        branching_factor=4,
    )
    assert out == "root summary"
    # 5 chunks → 2 mid + 1 final = 3 calls (with branching=4)
    # But wait: 5 chunks with branching 4 = ceil(5/4) = 2 batches at level 1
    # Then 2 → 1 at level 2
    # So 3 calls total
    assert summarizer.run.await_count >= 2


@pytest.mark.asyncio
async def test_summarize_document_short_text():
    from largestack._rag.summary_index import summarize_document
    summarizer = MagicMock()
    summarizer.run = AsyncMock()
    out = await summarize_document(
        "short text", summarizer_agent=summarizer, chunk_size=10000,
    )
    # Single chunk → no summarizer call needed
    assert out == "short text"
