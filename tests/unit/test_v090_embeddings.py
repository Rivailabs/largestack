"""v0.9.0: Tests for 6 new embedding providers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

respx = pytest.importorskip("respx")


# -------------------- Sentence Transformers --------------------


@pytest.mark.asyncio
async def test_sentence_transformers_no_dep_returns_error(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._integrations.embeddings_v09 import sentence_transformers_embed

    out = await sentence_transformers_embed("test")
    assert "sentence-transformers" in out


@pytest.mark.asyncio
async def test_sentence_transformers_empty_text():
    from largestack._integrations.embeddings_v09 import sentence_transformers_embed

    out = await sentence_transformers_embed("")
    assert "non-empty" in out


# -------------------- Ollama --------------------


@pytest.mark.asyncio
async def test_ollama_embed_success():
    from largestack._integrations.embeddings_v09 import ollama_embed

    fake_vec = [0.1] * 768
    with respx.mock() as mock:
        mock.post("http://localhost:11434/api/embeddings").respond(
            200,
            json={"embedding": fake_vec, "prompt_eval_count": 5},
        )
        out = await ollama_embed("hello world")
    body = json.loads(out)
    assert body["dim"] == 768
    assert body["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_ollama_embed_model_not_found():
    from largestack._integrations.embeddings_v09 import ollama_embed

    with respx.mock() as mock:
        mock.post("http://localhost:11434/api/embeddings").respond(404)
        out = await ollama_embed("test", model="nonsense")
    assert "not found" in out
    assert "ollama pull" in out


@pytest.mark.asyncio
async def test_ollama_embed_connection_error():
    from largestack._integrations.embeddings_v09 import ollama_embed
    import httpx

    with respx.mock() as mock:
        mock.post("http://localhost:11434/api/embeddings").mock(
            side_effect=httpx.ConnectError("conn refused")
        )
        out = await ollama_embed("test")
    assert "not reachable" in out


@pytest.mark.asyncio
async def test_ollama_embed_custom_base_url():
    from largestack._integrations.embeddings_v09 import ollama_embed

    with respx.mock() as mock:
        mock.post("http://my-ollama:11434/api/embeddings").respond(
            200, json={"embedding": [0.1, 0.2]}
        )
        out = await ollama_embed("hi", base_url="http://my-ollama:11434/")
    assert json.loads(out)["dim"] == 2


# -------------------- Nomic --------------------


@pytest.mark.asyncio
async def test_nomic_embed_no_key(monkeypatch):
    monkeypatch.delenv("LARGESTACK_NOMIC_API_KEY", raising=False)
    monkeypatch.delenv("NOMIC_API_KEY", raising=False)
    from largestack._integrations.embeddings_v09 import nomic_embed

    out = await nomic_embed("test")
    assert "LARGESTACK_NOMIC_API_KEY" in out


@pytest.mark.asyncio
async def test_nomic_embed_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOMIC_API_KEY", "fake")
    from largestack._integrations.embeddings_v09 import nomic_embed

    fake_vec = [0.0] * 768
    with respx.mock() as mock:
        mock.post("https://api-atlas.nomic.ai/v1/embedding/text").respond(
            200,
            json={"embeddings": [fake_vec], "usage": {"total_tokens": 10}},
        )
        out = await nomic_embed("hello")
    body = json.loads(out)
    assert body["dim"] == 768
    assert body["tokens"] == 10


@pytest.mark.asyncio
async def test_nomic_embed_auth_failure(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOMIC_API_KEY", "bad")
    from largestack._integrations.embeddings_v09 import nomic_embed

    with respx.mock() as mock:
        mock.post("https://api-atlas.nomic.ai/v1/embedding/text").respond(401)
        out = await nomic_embed("test")
    assert "auth failed" in out.lower()


# -------------------- Bedrock --------------------


@pytest.mark.asyncio
async def test_bedrock_embed_no_boto3(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._integrations.embeddings_v09 import bedrock_embed

    out = await bedrock_embed("test")
    assert "boto3" in out


@pytest.mark.asyncio
async def test_bedrock_embed_titan_v2():
    from largestack._integrations.embeddings_v09 import bedrock_embed

    fake_vec = [0.1] * 1024

    fake_body = MagicMock()
    fake_body.read = MagicMock(
        return_value=json.dumps(
            {
                "embedding": fake_vec,
                "inputTextTokenCount": 5,
            }
        ).encode()
    )
    fake_resp = {"body": fake_body}
    fake_client = MagicMock()
    fake_client.invoke_model = MagicMock(return_value=fake_resp)
    fake_boto3 = MagicMock()
    fake_boto3.client = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"boto3": fake_boto3}):
        out = await bedrock_embed("hello", model="amazon.titan-embed-text-v2:0")
    body = json.loads(out)
    assert body["dim"] == 1024
    assert body["tokens"] == 5

    # Verify body had dimensions+normalize for v2
    sent_body = json.loads(fake_client.invoke_model.call_args.kwargs["body"])
    assert sent_body["inputText"] == "hello"


@pytest.mark.asyncio
async def test_bedrock_embed_cohere_via_bedrock():
    from largestack._integrations.embeddings_v09 import bedrock_embed

    fake_vec = [0.1] * 1024

    fake_body = MagicMock()
    fake_body.read = MagicMock(
        return_value=json.dumps(
            {
                "embeddings": [fake_vec],
            }
        ).encode()
    )
    fake_resp = {"body": fake_body}
    fake_client = MagicMock()
    fake_client.invoke_model = MagicMock(return_value=fake_resp)
    fake_boto3 = MagicMock()
    fake_boto3.client = MagicMock(return_value=fake_client)

    with patch.dict("sys.modules", {"boto3": fake_boto3}):
        out = await bedrock_embed("hello", model="cohere.embed-english-v3")
    body = json.loads(out)
    assert body["dim"] == 1024


# -------------------- Vertex --------------------


@pytest.mark.asyncio
async def test_vertex_embed_no_project(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    from largestack._integrations.embeddings_v09 import vertex_embed

    out = await vertex_embed("test")
    assert "GOOGLE_CLOUD_PROJECT" in out


@pytest.mark.asyncio
async def test_vertex_embed_no_sdk(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fake-project")
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if "google.cloud" in name and "aiplatform" in name:
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._integrations.embeddings_v09 import vertex_embed

    out = await vertex_embed("test")
    assert "google-cloud-aiplatform" in out


# -------------------- Azure OpenAI --------------------


@pytest.mark.asyncio
async def test_azure_openai_embed_no_endpoint(monkeypatch):
    monkeypatch.delenv("LARGESTACK_AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    from largestack._integrations.embeddings_v09 import azure_openai_embed

    out = await azure_openai_embed("test", deployment="my-embed")
    assert "endpoint required" in out


@pytest.mark.asyncio
async def test_azure_openai_embed_no_key(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
    monkeypatch.delenv("LARGESTACK_AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    from largestack._integrations.embeddings_v09 import azure_openai_embed

    out = await azure_openai_embed("test", deployment="my-embed")
    assert "api_key required" in out


@pytest.mark.asyncio
async def test_azure_openai_embed_success(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    from largestack._integrations.embeddings_v09 import azure_openai_embed

    fake_vec = [0.1] * 1536
    with respx.mock() as mock:
        mock.post("https://x.openai.azure.com/openai/deployments/my-embed/embeddings").respond(
            200,
            json={"data": [{"embedding": fake_vec, "index": 0}], "usage": {"total_tokens": 5}},
        )
        out = await azure_openai_embed("hello", deployment="my-embed")
    body = json.loads(out)
    assert body["dim"] == 1536
    assert body["tokens"] == 5


# -------------------- All exposed --------------------


def test_all_v09_embeddings_exported():
    from largestack._integrations import (
        sentence_transformers_embed,
        ollama_embed,
        nomic_embed,
        bedrock_embed,
        vertex_embed,
        azure_openai_embed,
    )

    # Verify exposed in __all__
    from largestack import _integrations

    for name in [
        "sentence_transformers_embed",
        "ollama_embed",
        "nomic_embed",
        "bedrock_embed",
        "vertex_embed",
        "azure_openai_embed",
    ]:
        assert name in _integrations.__all__
