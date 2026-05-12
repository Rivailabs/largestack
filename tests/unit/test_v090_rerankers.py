"""v0.9.0: Tests for 3 new rerankers."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

respx = pytest.importorskip("respx")


# -------------------- Voyage Rerank --------------------

@pytest.mark.asyncio
async def test_voyage_rerank_no_key_returns_unchanged(monkeypatch):
    monkeypatch.delenv("LARGESTACK_VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    from largestack._rerankers import voyage_rerank
    docs = [{"id": "1", "content": "doc1"}, {"id": "2", "content": "doc2"}]
    result = await voyage_rerank("query", docs, top_k=2)
    assert len(result) == 2  # unchanged passthrough
    # No rerank_score added (since no rerank happened)
    assert all("rerank_score" not in d for d in result)


@pytest.mark.asyncio
async def test_voyage_rerank_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "vk_test")
    from largestack._rerankers import voyage_rerank
    docs = [
        {"id": "doc1", "content": "irrelevant"},
        {"id": "doc2", "content": "highly relevant"},
        {"id": "doc3", "content": "somewhat relevant"},
    ]
    fake_resp = {
        "data": [
            {"index": 1, "relevance_score": 0.95},
            {"index": 2, "relevance_score": 0.70},
            {"index": 0, "relevance_score": 0.10},
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.voyageai.com/v1/rerank").respond(200, json=fake_resp)
        result = await voyage_rerank("query", docs, top_k=2)
    assert len(result) == 2
    assert result[0]["id"] == "doc2"  # highest score
    assert result[0]["rerank_score"] == 0.95
    assert result[1]["id"] == "doc3"


@pytest.mark.asyncio
async def test_voyage_rerank_http_error_falls_through(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "x")
    from largestack._rerankers import voyage_rerank
    docs = [{"content": "a"}, {"content": "b"}]
    with respx.mock() as mock:
        mock.post("https://api.voyageai.com/v1/rerank").respond(500)
        result = await voyage_rerank("q", docs, top_k=2)
    assert len(result) == 2  # graceful fallback


@pytest.mark.asyncio
async def test_voyage_rerank_empty_docs():
    from largestack._rerankers import voyage_rerank
    result = await voyage_rerank("q", [])
    assert result == []


# -------------------- Jina Rerank --------------------

@pytest.mark.asyncio
async def test_jina_rerank_no_key_returns_unchanged(monkeypatch):
    monkeypatch.delenv("LARGESTACK_JINA_API_KEY", raising=False)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    from largestack._rerankers import jina_rerank
    docs = [{"content": "a"}, {"content": "b"}]
    result = await jina_rerank("q", docs, top_k=2)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_jina_rerank_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._rerankers import jina_rerank
    docs = [
        {"id": "a", "content": "first"},
        {"id": "b", "content": "second"},
    ]
    fake_resp = {
        "results": [
            {"index": 1, "relevance_score": 0.88},
            {"index": 0, "relevance_score": 0.32},
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.jina.ai/v1/rerank").respond(200, json=fake_resp)
        result = await jina_rerank("query", docs, top_k=2)
    assert result[0]["id"] == "b"
    assert result[0]["rerank_score"] == 0.88


@pytest.mark.asyncio
async def test_jina_rerank_handles_string_documents(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "x")
    from largestack._rerankers import jina_rerank
    docs = ["doc one", "doc two", "doc three"]
    fake_resp = {
        "results": [
            {"index": 2, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.1},
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.jina.ai/v1/rerank").respond(200, json=fake_resp)
        result = await jina_rerank("q", docs, top_k=2)
    assert result[0]["content"] == "doc three"


# -------------------- Cross-Encoder --------------------

@pytest.mark.asyncio
async def test_cross_encoder_no_dep_returns_unchanged(monkeypatch):
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._rerankers import cross_encoder_rerank
    docs = [{"content": "a"}, {"content": "b"}]
    result = await cross_encoder_rerank("q", docs, top_k=2)
    assert len(result) == 2  # graceful fallback


@pytest.mark.asyncio
async def test_cross_encoder_with_mocked_model():
    """When sentence-transformers IS available, scores are used."""
    fake_ce = MagicMock()
    # Higher score = more relevant
    fake_ce.predict = MagicMock(return_value=[0.2, 0.9, 0.5])

    fake_st = MagicMock()
    fake_st.CrossEncoder = MagicMock(return_value=fake_ce)

    with patch.dict("sys.modules", {"sentence_transformers": fake_st}):
        # Clear cache to force fresh load
        from largestack._rerankers import cross_encoder_rerank
        from largestack import _rerankers
        _rerankers._CE_MODELS.clear()

        docs = [
            {"id": "a", "content": "low relevance"},
            {"id": "b", "content": "high relevance"},
            {"id": "c", "content": "mid relevance"},
        ]
        result = await cross_encoder_rerank("query", docs, top_k=2)
    assert result[0]["id"] == "b"  # highest score 0.9
    assert result[0]["rerank_score"] == 0.9
    assert result[1]["id"] == "c"  # second highest 0.5


@pytest.mark.asyncio
async def test_cross_encoder_empty_docs():
    from largestack._rerankers import cross_encoder_rerank
    result = await cross_encoder_rerank("q", [])
    assert result == []
