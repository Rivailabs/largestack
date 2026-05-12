"""v0.8.0: Reranker tests (Cohere + RankGPT)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

respx = pytest.importorskip("respx")


# -------------------- Cohere --------------------

@pytest.mark.asyncio
async def test_cohere_rerank_reorders_by_relevance(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._rerankers import cohere_rerank

    docs = [
        {"id": "doc0", "content": "Random text about cats"},
        {"id": "doc1", "content": "How to deploy LARGESTACK in production"},
        {"id": "doc2", "content": "An article about cooking"},
    ]

    fake_resp = {
        "results": [
            {"index": 1, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.20},
            {"index": 2, "relevance_score": 0.10},
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/rerank").respond(200, json=fake_resp)
        out = await cohere_rerank("How do I deploy LARGESTACK?", docs, top_k=3)

    assert len(out) == 3
    assert out[0]["id"] == "doc1"
    assert out[0]["rerank_score"] == 0.95
    # Original metadata preserved
    assert out[0]["content"].startswith("How to deploy")


@pytest.mark.asyncio
async def test_cohere_rerank_top_k_limit(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._rerankers import cohere_rerank

    docs = [{"id": f"d{i}", "content": f"text {i}"} for i in range(10)]
    fake_resp = {
        "results": [
            {"index": i, "relevance_score": 1.0 - i * 0.1}
            for i in range(10)
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/rerank").respond(200, json=fake_resp)
        out = await cohere_rerank("q", docs, top_k=3)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_cohere_rerank_handles_plain_strings(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._rerankers import cohere_rerank

    docs = ["first", "second", "third"]
    fake_resp = {
        "results": [
            {"index": 2, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.5},
        ]
    }
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/rerank").respond(200, json=fake_resp)
        out = await cohere_rerank("q", docs, top_k=2)
    assert out[0]["content"] == "third"
    assert out[1]["content"] == "first"


@pytest.mark.asyncio
async def test_cohere_rerank_no_key_falls_back(monkeypatch):
    """No API key → returns docs in original order, doesn't crash."""
    monkeypatch.delenv("LARGESTACK_COHERE_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    from largestack._rerankers import cohere_rerank

    docs = [{"id": "a", "content": "X"}, {"id": "b", "content": "Y"}]
    out = await cohere_rerank("q", docs, top_k=5)
    assert len(out) == 2
    assert out[0]["id"] == "a"  # original order preserved


@pytest.mark.asyncio
async def test_cohere_rerank_api_error_falls_back(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._rerankers import cohere_rerank

    docs = [{"id": "a", "content": "X"}, {"id": "b", "content": "Y"}]
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/rerank").respond(500)
        out = await cohere_rerank("q", docs, top_k=5)
    # Still returns docs, original order
    assert len(out) == 2
    assert out[0]["id"] == "a"


@pytest.mark.asyncio
async def test_cohere_rerank_empty_docs():
    from largestack._rerankers import cohere_rerank
    assert await cohere_rerank("q", [], top_k=5) == []


@pytest.mark.asyncio
async def test_cohere_rerank_validates_top_k():
    from largestack._rerankers import cohere_rerank
    with pytest.raises(ValueError):
        await cohere_rerank("q", [{"content": "x"}], top_k=0)


# -------------------- RankGPT --------------------

@pytest.mark.asyncio
async def test_rankgpt_parses_standard_format():
    """LLM returns '[3] > [1] > [2]' → docs reordered."""
    from largestack._rerankers import rankgpt_rerank

    fake_result = MagicMock()
    fake_result.content = "[3] > [1] > [2]"
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    docs = [
        {"id": "first", "content": "doc 1"},
        {"id": "second", "content": "doc 2"},
        {"id": "third", "content": "doc 3"},
    ]
    out = await rankgpt_rerank("q", docs, agent=agent, top_k=3)
    assert out[0]["id"] == "third"
    assert out[1]["id"] == "first"
    assert out[2]["id"] == "second"
    # Higher rank → higher score
    assert out[0]["rerank_score"] > out[1]["rerank_score"]


@pytest.mark.asyncio
async def test_rankgpt_handles_alternative_formats():
    """LLM might output '3, 1, 2' or '3 > 1 > 2' — both should parse."""
    from largestack._rerankers import rankgpt_rerank
    docs = [{"id": str(i), "content": f"d{i}"} for i in range(3)]

    for output in ["3, 1, 2", "3 > 1 > 2", "Ranking: 3, 1, 2"]:
        fake_result = MagicMock()
        fake_result.content = output
        agent = MagicMock()
        agent.run = AsyncMock(return_value=fake_result)

        out = await rankgpt_rerank("q", docs, agent=agent, top_k=3)
        assert out[0]["id"] == "2"  # 1-indexed [3] → 0-indexed docs[2]


@pytest.mark.asyncio
async def test_rankgpt_appends_missing_indices():
    """If LLM forgets some docs, append them in original order."""
    from largestack._rerankers import rankgpt_rerank
    docs = [{"id": str(i), "content": f"d{i}"} for i in range(5)]

    fake_result = MagicMock()
    fake_result.content = "[2]"  # only ranks one
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    out = await rankgpt_rerank("q", docs, agent=agent, top_k=5)
    assert len(out) == 5
    assert out[0]["id"] == "1"  # 1-indexed [2] → docs[1]
    # Remaining appended in original order
    appended_ids = [d["id"] for d in out[1:]]
    assert appended_ids == ["0", "2", "3", "4"]


@pytest.mark.asyncio
async def test_rankgpt_truncates_long_docs():
    from largestack._rerankers import rankgpt_rerank
    long_text = "x" * 5000
    docs = [{"id": "a", "content": long_text}]

    fake_result = MagicMock()
    fake_result.content = "[1]"
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    await rankgpt_rerank("q", docs, agent=agent, top_k=1, max_doc_chars=100)

    prompt = agent.run.await_args.args[0]
    # The truncated version should appear, not the full
    assert "..." in prompt
    assert "x" * 5000 not in prompt


@pytest.mark.asyncio
async def test_rankgpt_handles_llm_failure():
    from largestack._rerankers import rankgpt_rerank
    docs = [{"id": "a", "content": "x"}]
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("boom"))

    out = await rankgpt_rerank("q", docs, agent=agent, top_k=5)
    assert len(out) == 1  # falls back to original
    assert out[0]["id"] == "a"


@pytest.mark.asyncio
async def test_rankgpt_validates():
    from largestack._rerankers import rankgpt_rerank
    with pytest.raises(ValueError):
        await rankgpt_rerank("q", [{"content": "x"}], agent=MagicMock(), top_k=0)
