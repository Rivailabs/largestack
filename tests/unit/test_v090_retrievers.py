"""v0.9.0: Tests for compression, self-query, ensemble-v2 retrievers."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Compression Retriever --------------------

@pytest.mark.asyncio
async def test_compression_extracts_relevant_sentences():
    from largestack._retrievers import compression_retrieve

    base_docs = [
        {"id": "1", "content": "Random sentence. Relevant: pgvector uses HNSW indexes. Random again."},
        {"id": "2", "content": "Cooking recipes for pasta. Tomato sauce. Garlic."},
    ]
    retriever = AsyncMock(return_value=base_docs)
    compressor = MagicMock()
    compressor.run = AsyncMock(side_effect=[
        MagicMock(content="pgvector uses HNSW indexes."),
        MagicMock(content="NONE"),  # cooking is not relevant
    ])

    out = await compression_retrieve(
        "How does pgvector work?",
        retriever=retriever,
        compressor_agent=compressor,
        k=2,
    )
    # Doc 2 dropped (NONE), doc 1 has compressed_content
    assert len(out) == 1
    assert out[0]["id"] == "1"
    assert out[0]["compressed_content"] == "pgvector uses HNSW indexes."


@pytest.mark.asyncio
async def test_compression_handles_no_base_results():
    from largestack._retrievers import compression_retrieve
    retriever = AsyncMock(return_value=[])
    compressor = MagicMock()
    out = await compression_retrieve(
        "q", retriever=retriever, compressor_agent=compressor,
    )
    assert out == []


@pytest.mark.asyncio
async def test_compression_truncates_long_output():
    from largestack._retrievers import compression_retrieve

    long_content = "x" * 10000
    retriever = AsyncMock(return_value=[{"id": "1", "content": "doc"}])
    compressor = MagicMock()
    compressor.run = AsyncMock(return_value=MagicMock(content=long_content))

    out = await compression_retrieve(
        "q", retriever=retriever, compressor_agent=compressor,
        max_chars_per_doc=100,
    )
    assert len(out[0]["compressed_content"]) <= 200  # 100 + truncation marker
    assert "[truncated]" in out[0]["compressed_content"]


@pytest.mark.asyncio
async def test_compression_handles_compressor_failure():
    """If LLM fails, fall back to using truncated original content."""
    from largestack._retrievers import compression_retrieve
    retriever = AsyncMock(return_value=[{"id": "1", "content": "original content"}])
    compressor = MagicMock()
    compressor.run = AsyncMock(side_effect=RuntimeError("LLM down"))

    out = await compression_retrieve(
        "q", retriever=retriever, compressor_agent=compressor,
    )
    # Falls back to truncated original
    assert len(out) == 1
    assert "compressed_content" in out[0]


# -------------------- Self-Query Retriever --------------------

@pytest.mark.asyncio
async def test_self_query_extracts_filters():
    from largestack._retrievers import self_query_retrieve

    parser = MagicMock()
    parser.run = AsyncMock(return_value=MagicMock(
        content='{"search_text": "blog posts about Rust", "filters": {"year": 2023, "type": "blog"}}'
    ))
    retriever = AsyncMock(return_value=[
        {"id": "1", "content": "Rust blog post"},
    ])

    out = await self_query_retrieve(
        "Find blog posts about Rust from 2023",
        retriever=retriever,
        parser_agent=parser,
        metadata_fields={
            "year": "publication year (int)",
            "type": "doc type",
        },
    )
    # Verify retriever was called with filter
    retriever.assert_awaited_once()
    call_kw = retriever.await_args.kwargs
    assert call_kw["filter"] == {"year": 2023, "type": "blog"}
    assert len(out) == 1


@pytest.mark.asyncio
async def test_self_query_strips_unknown_filter_fields():
    """Filters not in metadata_fields are dropped (security)."""
    from largestack._retrievers import self_query_retrieve

    parser = MagicMock()
    parser.run = AsyncMock(return_value=MagicMock(
        content='{"search_text": "x", "filters": {"year": 2023, "secret_field": "exfiltrate"}}'
    ))
    retriever = AsyncMock(return_value=[])

    await self_query_retrieve(
        "q",
        retriever=retriever,
        parser_agent=parser,
        metadata_fields={"year": "year"},  # only year is allowed
    )
    call_kw = retriever.await_args.kwargs
    # secret_field stripped
    assert "secret_field" not in call_kw["filter"]
    assert call_kw["filter"] == {"year": 2023}


@pytest.mark.asyncio
async def test_self_query_falls_back_on_parse_failure():
    """If LLM returns garbage, run plain semantic search."""
    from largestack._retrievers import self_query_retrieve

    parser = MagicMock()
    parser.run = AsyncMock(return_value=MagicMock(content="not valid JSON"))
    retriever = AsyncMock(return_value=[])

    await self_query_retrieve(
        "original query",
        retriever=retriever,
        parser_agent=parser,
        metadata_fields={"year": "y"},
    )
    # Falls back to original query, no filters
    call_kw = retriever.await_args.kwargs
    assert call_kw.get("filter", {}) == {}


@pytest.mark.asyncio
async def test_self_query_strips_code_fences():
    from largestack._retrievers import self_query_retrieve

    parser = MagicMock()
    parser.run = AsyncMock(return_value=MagicMock(
        content='```json\n{"search_text": "test", "filters": {}}\n```'
    ))
    retriever = AsyncMock(return_value=[])

    await self_query_retrieve(
        "q", retriever=retriever, parser_agent=parser,
        metadata_fields={"y": "y"},
    )
    # Should NOT have raised; should have parsed despite the fences
    retriever.assert_awaited()


# -------------------- Ensemble v2 Retriever --------------------

@pytest.mark.asyncio
async def test_ensemble_v2_rrf_fusion():
    from largestack._retrievers import ensemble_v2_retrieve

    r1 = AsyncMock(return_value=[
        {"id": "a", "score": 0.9},
        {"id": "b", "score": 0.7},
    ])
    r2 = AsyncMock(return_value=[
        {"id": "b", "score": 0.95},
        {"id": "c", "score": 0.6},
    ])

    out = await ensemble_v2_retrieve(
        "q", retrievers=[(r1, 1.0), (r2, 1.0)], k=3, fusion="rrf",
    )
    # Doc b appears in both → highest fused score
    ids = [d["id"] for d in out]
    assert ids[0] == "b"


@pytest.mark.asyncio
async def test_ensemble_v2_weighted_score():
    from largestack._retrievers import ensemble_v2_retrieve

    r1 = AsyncMock(return_value=[{"id": "a", "score": 0.5}])
    r2 = AsyncMock(return_value=[{"id": "a", "score": 0.5}])

    out = await ensemble_v2_retrieve(
        "q",
        retrievers=[(r1, 2.0), (r2, 1.0)],  # r1 weighted 2x
        fusion="weighted_score",
    )
    # Combined: 2.0 * 0.5 + 1.0 * 0.5 = 1.5
    assert abs(out[0]["fusion_score"] - 1.5) < 1e-6


@pytest.mark.asyncio
async def test_ensemble_v2_max_score():
    from largestack._retrievers import ensemble_v2_retrieve

    r1 = AsyncMock(return_value=[{"id": "a", "score": 0.3}])
    r2 = AsyncMock(return_value=[{"id": "a", "score": 0.9}])

    out = await ensemble_v2_retrieve(
        "q", retrievers=[(r1, 1.0), (r2, 1.0)], fusion="max_score",
    )
    # Max of 0.3 and 0.9 = 0.9
    assert abs(out[0]["fusion_score"] - 0.9) < 1e-6


@pytest.mark.asyncio
async def test_ensemble_v2_empty_retrievers():
    from largestack._retrievers import ensemble_v2_retrieve
    out = await ensemble_v2_retrieve("q", retrievers=[])
    assert out == []


@pytest.mark.asyncio
async def test_ensemble_v2_unknown_fusion_raises():
    from largestack._retrievers import ensemble_v2_retrieve
    r = AsyncMock(return_value=[{"id": "a"}])
    with pytest.raises(ValueError, match="unknown fusion"):
        await ensemble_v2_retrieve(
            "q", retrievers=[(r, 1.0)], fusion="bogus_fusion",
        )


@pytest.mark.asyncio
async def test_ensemble_v2_handles_failed_retriever():
    """If one retriever fails, others still contribute."""
    from largestack._retrievers import ensemble_v2_retrieve

    r1 = AsyncMock(side_effect=RuntimeError("dead"))
    r2 = AsyncMock(return_value=[{"id": "a", "score": 0.8}])

    out = await ensemble_v2_retrieve(
        "q", retrievers=[(r1, 1.0), (r2, 1.0)],
    )
    # Should still return r2's result
    assert len(out) == 1
    assert out[0]["id"] == "a"


@pytest.mark.asyncio
async def test_ensemble_v2_runs_in_parallel():
    """Retrievers should be awaited concurrently for speed."""
    import asyncio
    from largestack._retrievers import ensemble_v2_retrieve

    async def slow_r(query, k=5):
        await asyncio.sleep(0.05)
        return [{"id": "x", "score": 1.0}]

    import time
    start = time.time()
    out = await ensemble_v2_retrieve(
        "q",
        retrievers=[(slow_r, 1.0), (slow_r, 1.0), (slow_r, 1.0)],
    )
    elapsed = time.time() - start
    # 3 parallel 0.05s calls should be ~0.05s, not 0.15s
    assert elapsed < 0.12
    assert len(out) >= 1
