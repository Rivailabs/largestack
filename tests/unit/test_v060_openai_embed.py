"""v0.6.0: OpenAI Embeddings integration tests."""
from __future__ import annotations

import json
import pytest

respx = pytest.importorskip("respx")


@pytest.mark.asyncio
async def test_openai_embed_no_key_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_OPENAI_API_KEY", raising=False)
    from largestack._integrations.openai_embeddings import openai_embed
    out = await openai_embed("hello world")
    assert "LARGESTACK_OPENAI_API_KEY" in out


@pytest.mark.asyncio
async def test_openai_embed_empty_text(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-fake-test")
    from largestack._integrations.openai_embeddings import openai_embed
    out = await openai_embed("")
    assert "non-empty" in out


@pytest.mark.asyncio
async def test_openai_embed_text_too_long(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-fake-test")
    from largestack._integrations.openai_embeddings import openai_embed
    out = await openai_embed("x" * 33000)
    assert "too long" in out


@pytest.mark.asyncio
async def test_openai_embed_unknown_model(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-fake-test")
    from largestack._integrations.openai_embeddings import openai_embed
    out = await openai_embed("hello", model="nonsense-model")
    assert "unknown model" in out


@pytest.mark.asyncio
async def test_openai_embed_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-fake-test")
    from largestack._integrations.openai_embeddings import openai_embed
    fake_embedding = [0.1, 0.2, 0.3] * 512  # 1536-dim
    with respx.mock() as mock:
        mock.post("https://api.openai.com/v1/embeddings").respond(
            200, json={
                "data": [{"embedding": fake_embedding, "index": 0}],
                "usage": {"total_tokens": 5},
            },
        )
        out = await openai_embed("hello world")

    body = json.loads(out)
    assert body["model"] == "text-embedding-3-small"
    assert body["dim"] == 1536
    assert body["tokens"] == 5
    assert len(body["embedding"]) == 1536


@pytest.mark.asyncio
async def test_openai_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-bad")
    from largestack._integrations.openai_embeddings import openai_embed
    with respx.mock() as mock:
        mock.post("https://api.openai.com/v1/embeddings").respond(401)
        out = await openai_embed("test")
    assert "auth failed" in out.lower() or "401" in out


@pytest.mark.asyncio
async def test_openai_embed_rate_limit(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "sk-fake")
    from largestack._integrations.openai_embeddings import openai_embed
    with respx.mock() as mock:
        mock.post("https://api.openai.com/v1/embeddings").respond(429)
        out = await openai_embed("test")
    assert "rate limited" in out.lower()


def test_openai_embed_in_integrations_init():
    from largestack import _integrations
    assert "openai_embed" in _integrations.__all__
    assert hasattr(_integrations, "openai_embed")
