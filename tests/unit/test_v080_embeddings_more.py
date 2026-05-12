"""v0.8.0: HuggingFace + Jina embedding tests."""
from __future__ import annotations

import json
import pytest

respx = pytest.importorskip("respx")


# -------------------- HuggingFace --------------------

@pytest.mark.asyncio
async def test_hf_embed_no_key(monkeypatch):
    for k in ("LARGESTACK_HF_API_KEY", "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from largestack._integrations.hf_embed import hf_embed
    out = await hf_embed("hello")
    assert "LARGESTACK_HF_API_KEY" in out


@pytest.mark.asyncio
async def test_hf_embed_empty_text(monkeypatch):
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "fake")
    from largestack._integrations.hf_embed import hf_embed
    out = await hf_embed("")
    assert "non-empty" in out


@pytest.mark.asyncio
async def test_hf_embed_text_too_long(monkeypatch):
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "fake")
    from largestack._integrations.hf_embed import hf_embed
    out = await hf_embed("x" * 33000)
    assert "too long" in out


@pytest.mark.asyncio
async def test_hf_embed_success_flat_response(monkeypatch):
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "fake")
    from largestack._integrations.hf_embed import hf_embed
    fake_vec = [0.1] * 384
    with respx.mock() as mock:
        mock.post(
            "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
        ).respond(200, json=fake_vec)
        out = await hf_embed("hello world")
    body = json.loads(out)
    assert body["dim"] == 384
    assert body["model"] == "sentence-transformers/all-MiniLM-L6-v2"


@pytest.mark.asyncio
async def test_hf_embed_success_wrapped_response(monkeypatch):
    """Some HF models return [[0.1, 0.2, ...]] (wrapped)."""
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "fake")
    from largestack._integrations.hf_embed import hf_embed
    fake_vec = [[0.1] * 768]
    with respx.mock() as mock:
        mock.post(
            "https://api-inference.huggingface.co/pipeline/feature-extraction/BAAI/bge-base-en-v1.5"
        ).respond(200, json=fake_vec)
        out = await hf_embed("hello", model="BAAI/bge-base-en-v1.5")
    body = json.loads(out)
    assert body["dim"] == 768


@pytest.mark.asyncio
async def test_hf_embed_503_loading(monkeypatch):
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "fake")
    from largestack._integrations.hf_embed import hf_embed
    with respx.mock() as mock:
        mock.post(
            "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
        ).respond(503)
        out = await hf_embed("hi")
    assert "loading" in out.lower()


@pytest.mark.asyncio
async def test_hf_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_HF_API_KEY", "bad")
    from largestack._integrations.hf_embed import hf_embed
    with respx.mock() as mock:
        mock.post(
            "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
        ).respond(401)
        out = await hf_embed("test")
    assert "auth failed" in out.lower()


def test_hf_normalize_per_token_vectors():
    """Some HF models return [N_tokens, dim] arrays — should mean-pool."""
    from largestack._integrations.hf_embed import _normalize_embedding
    # 3 tokens, 4-dim each
    data = [[[1.0, 2.0, 3.0, 4.0], [3.0, 4.0, 5.0, 6.0], [5.0, 6.0, 7.0, 8.0]]]
    vec = _normalize_embedding(data)
    assert vec == [3.0, 4.0, 5.0, 6.0]  # mean per dim


def test_hf_normalize_handles_invalid_shape():
    from largestack._integrations.hf_embed import _normalize_embedding
    assert _normalize_embedding([]) is None
    assert _normalize_embedding({"weird": "shape"}) is None
    assert _normalize_embedding(None) is None


def test_hf_embed_in_integrations_init():
    from largestack import _integrations
    assert "hf_embed" in _integrations.__all__


# -------------------- Jina --------------------

@pytest.mark.asyncio
async def test_jina_embed_no_key(monkeypatch):
    monkeypatch.delenv("LARGESTACK_JINA_API_KEY", raising=False)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    from largestack._integrations.jina_embed import jina_embed
    out = await jina_embed("hello")
    assert "LARGESTACK_JINA_API_KEY" in out


@pytest.mark.asyncio
async def test_jina_embed_unknown_model(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._integrations.jina_embed import jina_embed
    out = await jina_embed("hi", model="bogus")
    assert "unknown model" in out


@pytest.mark.asyncio
async def test_jina_embed_invalid_task(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._integrations.jina_embed import jina_embed
    out = await jina_embed("hi", task="random_task")
    assert "invalid task" in out


@pytest.mark.asyncio
async def test_jina_embed_dimension_only_v3(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._integrations.jina_embed import jina_embed
    out = await jina_embed("hi", model="jina-embeddings-v2-base-en", output_dimension=512)
    assert "only supported on" in out


@pytest.mark.asyncio
async def test_jina_embed_dimension_range(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._integrations.jina_embed import jina_embed
    out = await jina_embed("hi", output_dimension=100)
    assert "[256, 1024]" in out


@pytest.mark.asyncio
async def test_jina_embed_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "fake")
    from largestack._integrations.jina_embed import jina_embed
    fake_vec = [0.05] * 1024
    with respx.mock() as mock:
        mock.post("https://api.jina.ai/v1/embeddings").respond(
            200,
            json={
                "data": [{"embedding": fake_vec, "index": 0}],
                "model": "jina-embeddings-v3",
                "usage": {"total_tokens": 8},
            },
        )
        out = await jina_embed("hello world", task="retrieval.query")
    body = json.loads(out)
    assert body["dim"] == 1024
    assert body["tokens"] == 8


@pytest.mark.asyncio
async def test_jina_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JINA_API_KEY", "bad")
    from largestack._integrations.jina_embed import jina_embed
    with respx.mock() as mock:
        mock.post("https://api.jina.ai/v1/embeddings").respond(401)
        out = await jina_embed("test")
    assert "auth failed" in out.lower()


def test_jina_embed_in_integrations_init():
    from largestack import _integrations
    assert "jina_embed" in _integrations.__all__
