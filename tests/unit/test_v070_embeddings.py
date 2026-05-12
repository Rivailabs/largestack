"""v0.7.0: Cohere and Voyage embeddings tests."""
from __future__ import annotations

import json
import pytest

respx = pytest.importorskip("respx")


# -------------------- Cohere --------------------

@pytest.mark.asyncio
async def test_cohere_embed_no_key_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_COHERE_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    from largestack._integrations.cohere_embed import cohere_embed
    out = await cohere_embed("hello")
    assert "LARGESTACK_COHERE_API_KEY" in out


@pytest.mark.asyncio
async def test_cohere_embed_empty_text(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    out = await cohere_embed("")
    assert "non-empty" in out


@pytest.mark.asyncio
async def test_cohere_embed_text_too_long(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    out = await cohere_embed("x" * 33000)
    assert "too long" in out


@pytest.mark.asyncio
async def test_cohere_embed_unknown_model(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    out = await cohere_embed("hi", model="nonsense")
    assert "unknown model" in out


@pytest.mark.asyncio
async def test_cohere_embed_invalid_dimension(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    out = await cohere_embed("hi", output_dimension=999)
    assert "output_dimension" in out


@pytest.mark.asyncio
async def test_cohere_embed_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    fake_vec = [0.1, 0.2, 0.3] * 341 + [0.5]  # 1024-dim
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/embed").respond(
            200,
            json={
                "embeddings": {"float": [fake_vec]},
                "meta": {"billed_units": {"input_tokens": 5}},
            },
        )
        out = await cohere_embed("hello world")
    body = json.loads(out)
    assert body["model"] == "embed-v4.0"
    assert body["dim"] == 1024
    assert body["tokens"] == 5
    assert len(body["embedding"]) == 1024


@pytest.mark.asyncio
async def test_cohere_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "bad")
    from largestack._integrations.cohere_embed import cohere_embed
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/embed").respond(401)
        out = await cohere_embed("test")
    assert "auth failed" in out.lower()


@pytest.mark.asyncio
async def test_cohere_embed_rate_limit(monkeypatch):
    monkeypatch.setenv("LARGESTACK_COHERE_API_KEY", "fake")
    from largestack._integrations.cohere_embed import cohere_embed
    with respx.mock() as mock:
        mock.post("https://api.cohere.com/v2/embed").respond(429)
        out = await cohere_embed("test")
    assert "rate limited" in out.lower()


def test_cohere_embed_in_integrations_init():
    from largestack import _integrations
    assert "cohere_embed" in _integrations.__all__


# -------------------- Voyage --------------------

@pytest.mark.asyncio
async def test_voyage_embed_no_key_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    from largestack._integrations.voyage_embed import voyage_embed
    out = await voyage_embed("hello")
    assert "LARGESTACK_VOYAGE_API_KEY" in out


@pytest.mark.asyncio
async def test_voyage_embed_unknown_model(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "fake")
    from largestack._integrations.voyage_embed import voyage_embed
    out = await voyage_embed("hi", model="nonsense-v99")
    assert "unknown model" in out


@pytest.mark.asyncio
async def test_voyage_embed_invalid_input_type(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "fake")
    from largestack._integrations.voyage_embed import voyage_embed
    out = await voyage_embed("hi", input_type="banana")
    assert "input_type" in out


@pytest.mark.asyncio
async def test_voyage_embed_dimension_unsupported_for_model(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "fake")
    from largestack._integrations.voyage_embed import voyage_embed
    out = await voyage_embed("hi", model="voyage-finance-2", output_dimension=512)
    assert "doesn't support" in out


@pytest.mark.asyncio
async def test_voyage_embed_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "fake")
    from largestack._integrations.voyage_embed import voyage_embed
    fake_vec = [0.0] * 1024
    with respx.mock() as mock:
        mock.post("https://api.voyageai.com/v1/embeddings").respond(
            200,
            json={
                "object": "list",
                "data": [{"embedding": fake_vec, "index": 0}],
                "model": "voyage-3.5",
                "usage": {"total_tokens": 10},
            },
        )
        out = await voyage_embed("hello", input_type="document")
    body = json.loads(out)
    assert body["model"] == "voyage-3.5"
    assert body["dim"] == 1024
    assert body["tokens"] == 10


@pytest.mark.asyncio
async def test_voyage_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_VOYAGE_API_KEY", "bad")
    from largestack._integrations.voyage_embed import voyage_embed
    with respx.mock() as mock:
        mock.post("https://api.voyageai.com/v1/embeddings").respond(401)
        out = await voyage_embed("test")
    assert "auth failed" in out.lower()


def test_voyage_embed_in_integrations_init():
    from largestack import _integrations
    assert "voyage_embed" in _integrations.__all__
