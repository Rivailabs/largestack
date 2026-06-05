"""Additional embedding providers (v0.9.0).

Six more embedding integrations on top of v0.7's Cohere/Voyage and
v0.8's HuggingFace/Jina:

- ``sentence_transformers_embed`` — local model (BGE, E5, GTE, etc.)
- ``ollama_embed`` — local Ollama server
- ``nomic_embed`` — Nomic Atlas API
- ``bedrock_embed`` — AWS Bedrock Titan / Cohere via Bedrock
- ``vertex_embed`` — Google Vertex AI text-embedding
- ``azure_openai_embed`` — Azure OpenAI Service

All return JSON ``{model, dim, tokens, embedding}`` strings or error
strings. Never raise.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.embeddings_v09")


# -------------------- Sentence Transformers (local) --------------------

# Cache for loaded models (one per process)
_ST_MODELS: dict = {}


@tool(timeout=60)
async def sentence_transformers_embed(
    text: str,
    model: str = "all-MiniLM-L6-v2",
    *,
    normalize: bool = True,
) -> str:
    """Generate embeddings using sentence-transformers (local, no API).

    Popular models:
    - ``all-MiniLM-L6-v2`` — 384d, fast, default
    - ``all-mpnet-base-v2`` — 768d, more accurate
    - ``BAAI/bge-large-en-v1.5`` — 1024d, SOTA for retrieval
    - ``intfloat/e5-large-v2`` — 1024d, strong retrieval
    - ``thenlper/gte-large`` — 1024d, multilingual

    Requires: ``pip install sentence-transformers torch``.

    Args:
        text: input text (max ~512 tokens for most models).
        model: HuggingFace model name.
        normalize: L2-normalize output (recommended for cosine similarity).

    Note: First call loads the model (slow, GBs of weights). Subsequent
    calls are fast — model is cached in process memory.
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return "error: sentence-transformers not installed (pip install sentence-transformers)"

    try:
        if model not in _ST_MODELS:
            log.info(f"loading sentence-transformers model: {model}")
            _ST_MODELS[model] = SentenceTransformer(model)
        st_model = _ST_MODELS[model]

        # Run inference in a thread to avoid blocking the event loop
        import asyncio
        vec = await asyncio.to_thread(
            st_model.encode, text, normalize_embeddings=normalize,
        )
        vec_list = [float(x) for x in vec]
    except Exception as e:
        return f"error: sentence-transformers encode failed: {e}"

    return json.dumps({
        "model": model,
        "dim": len(vec_list),
        "tokens": len(text.split()),  # approximation
        "embedding": vec_list,
    })


# -------------------- Ollama (local) --------------------

@tool(timeout=60)
async def ollama_embed(
    text: str,
    model: str = "nomic-embed-text",
    base_url: str | None = None,
) -> str:
    """Generate embeddings via local Ollama server.

    Popular Ollama embedding models:
    - ``nomic-embed-text`` — 768d, default
    - ``mxbai-embed-large`` — 1024d
    - ``snowflake-arctic-embed`` — 1024d
    - ``all-minilm`` — 384d

    Args:
        text: input text.
        model: Ollama model name (must be pulled: ``ollama pull <name>``).
        base_url: Ollama server URL (else ``OLLAMA_BASE_URL`` env or localhost).

    Returns: JSON or error string.
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    base = base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    base = base.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{base}/api/embeddings",
                json={"model": model, "prompt": text},
            )
        if r.status_code == 404:
            return f"error: Ollama model {model!r} not found (run: ollama pull {model})"
        if r.status_code >= 400:
            return f"error: Ollama HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.ConnectError:
        return f"error: Ollama not reachable at {base} (is it running?)"
    except Exception as e:
        return f"error: Ollama request failed: {e}"

    vec = data.get("embedding") or data.get("embeddings")
    if isinstance(vec, list) and vec and isinstance(vec[0], list):
        vec = vec[0]  # some Ollama versions wrap in list
    if not vec:
        return "error: no embedding in Ollama response"

    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": data.get("prompt_eval_count", 0),
        "embedding": vec,
    })


# -------------------- Nomic Atlas --------------------

@tool(timeout=30)
async def nomic_embed(
    text: str,
    model: str = "nomic-embed-text-v1.5",
    task_type: str = "search_document",
) -> str:
    """Nomic Atlas hosted embedding API.

    Auth: ``LARGESTACK_NOMIC_API_KEY`` or ``NOMIC_API_KEY`` env var.

    Args:
        text: input text.
        model: Nomic model name. ``nomic-embed-text-v1.5`` (768d, default)
            or ``nomic-embed-text-v1`` (768d).
        task_type: ``search_document`` (default), ``search_query``,
            ``classification``, or ``clustering``.

    Endpoint: https://api-atlas.nomic.ai/v1/embedding/text
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    api_key = (
        os.environ.get("LARGESTACK_NOMIC_API_KEY")
        or os.environ.get("NOMIC_API_KEY", "")
    )
    if not api_key:
        return "error: LARGESTACK_NOMIC_API_KEY (or NOMIC_API_KEY) not set"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api-atlas.nomic.ai/v1/embedding/text",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "texts": [text],
                    "task_type": task_type,
                },
            )
        if r.status_code == 401:
            return "error: Nomic auth failed"
        if r.status_code == 429:
            return "error: Nomic rate limited"
        if r.status_code >= 400:
            return f"error: Nomic HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.TimeoutException:
        return "error: Nomic request timed out"
    except Exception as e:
        return f"error: Nomic request failed: {e}"

    embeddings = data.get("embeddings") or []
    if not embeddings:
        return "error: no embedding in Nomic response"
    vec = embeddings[0]
    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": data.get("usage", {}).get("total_tokens", 0),
        "embedding": vec,
    })


# -------------------- AWS Bedrock --------------------

@tool(timeout=30)
async def bedrock_embed(
    text: str,
    model: str = "amazon.titan-embed-text-v2:0",
    *,
    region: str | None = None,
    dimensions: int | None = None,
) -> str:
    """AWS Bedrock embeddings.

    Auth: standard AWS env vars (AWS_ACCESS_KEY_ID etc.) or instance profile.
    Requires: ``pip install boto3``.

    Supported models:
    - ``amazon.titan-embed-text-v2:0`` — 1024d default, 256/512/1024 supported
    - ``amazon.titan-embed-text-v1`` — 1536d
    - ``cohere.embed-english-v3`` — 1024d
    - ``cohere.embed-multilingual-v3`` — 1024d

    Args:
        text: input text.
        model: Bedrock model ID.
        region: AWS region (else AWS_DEFAULT_REGION env).
        dimensions: optional output dimension (Titan v2 only — 256/512/1024).
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    try:
        import boto3
    except ImportError:
        return "error: boto3 not installed (pip install boto3)"

    region = region or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        # Build request body per model family
        if "titan-embed" in model:
            body: dict = {"inputText": text}
            if dimensions and "v2" in model:
                body["dimensions"] = dimensions
                body["normalize"] = True
        elif "cohere.embed" in model:
            body = {"texts": [text], "input_type": "search_document"}
        else:
            body = {"inputText": text}

        import asyncio as _asyncio
        resp = await _asyncio.to_thread(
            client.invoke_model,
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
    except Exception as e:
        return f"error: Bedrock invoke failed: {e}"

    # Parse per model family
    if "embedding" in result:
        vec = result["embedding"]
    elif "embeddings" in result:
        embs = result["embeddings"]
        vec = embs[0] if isinstance(embs, list) and embs else None
        if isinstance(vec, dict):
            # Cohere via Bedrock returns nested format
            vec = vec.get("float") or vec.get("embedding")
    else:
        return f"error: unrecognized Bedrock response: {list(result.keys())}"

    if not vec:
        return "error: no embedding returned from Bedrock"

    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": result.get("inputTextTokenCount", 0),
        "embedding": vec,
    })


# -------------------- Google Vertex AI --------------------

@tool(timeout=30)
async def vertex_embed(
    text: str,
    model: str = "text-embedding-004",
    *,
    project: str | None = None,
    location: str = "us-central1",
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> str:
    """Google Vertex AI text embeddings.

    Auth: ``GOOGLE_APPLICATION_CREDENTIALS`` env var → service account JSON,
    OR ``gcloud auth application-default login``.

    Requires: ``pip install google-cloud-aiplatform``.

    Models:
    - ``text-embedding-004`` — current default, 768d
    - ``text-embedding-005`` — newer
    - ``text-multilingual-embedding-002`` — multilingual

    Args:
        text: input text.
        model: Vertex model name (without ``projects/...`` prefix).
        project: GCP project ID (else GOOGLE_CLOUD_PROJECT env).
        location: region.
        task_type: ``RETRIEVAL_DOCUMENT`` (default), ``RETRIEVAL_QUERY``,
            ``SEMANTIC_SIMILARITY``, ``CLASSIFICATION``, ``CLUSTERING``.
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return "error: project arg or GOOGLE_CLOUD_PROJECT env var required"

    try:
        from google.cloud import aiplatform_v1
        from google.cloud.aiplatform_v1.types import PredictRequest
    except ImportError:
        return "error: google-cloud-aiplatform not installed"

    try:
        endpoint = (
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/{model}"
        )
        client = aiplatform_v1.PredictionServiceAsyncClient(
            client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        )
        instance = {"content": text, "task_type": task_type}
        from google.protobuf.struct_pb2 import Value
        from google.protobuf import json_format
        instance_pb = Value()
        json_format.ParseDict(instance, instance_pb)
        resp = await client.predict(
            endpoint=endpoint, instances=[instance_pb],
        )
        # Predictions come back as Value protobufs
        from google.protobuf.json_format import MessageToDict
        first_pred = MessageToDict(resp.predictions[0])
        vec = first_pred.get("embeddings", {}).get("values") or []
        token_count = first_pred.get("embeddings", {}).get(
            "statistics", {}
        ).get("token_count", 0)
    except Exception as e:
        return f"error: Vertex predict failed: {e}"

    if not vec:
        return "error: no embedding returned from Vertex"
    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": int(token_count or 0),
        "embedding": vec,
    })


# -------------------- Azure OpenAI Service --------------------

@tool(timeout=30)
async def azure_openai_embed(
    text: str,
    deployment: str,
    *,
    endpoint: str | None = None,
    api_key: str | None = None,
    api_version: str = "2024-02-15-preview",
) -> str:
    """Azure OpenAI Service embeddings.

    Args:
        text: input text.
        deployment: your Azure deployment name (NOT the model name).
        endpoint: ``https://{resource}.openai.azure.com`` (or
            ``AZURE_OPENAI_ENDPOINT`` env var).
        api_key: API key (or ``AZURE_OPENAI_API_KEY`` env var).
        api_version: API version string.
    """
    if not isinstance(text, str) or not text:
        return "error: text must be a non-empty string"

    endpoint = (
        endpoint
        or os.environ.get("LARGESTACK_AZURE_OPENAI_ENDPOINT")
        or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    )
    api_key = (
        api_key
        or os.environ.get("LARGESTACK_AZURE_OPENAI_API_KEY")
        or os.environ.get("AZURE_OPENAI_API_KEY", "")
    )
    if not endpoint:
        return "error: Azure endpoint required (AZURE_OPENAI_ENDPOINT)"
    if not api_key:
        return "error: Azure api_key required (AZURE_OPENAI_API_KEY)"

    endpoint = endpoint.rstrip("/")
    url = (
        f"{endpoint}/openai/deployments/{deployment}/embeddings"
        f"?api-version={api_version}"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={"input": text},
            )
        if r.status_code == 401:
            return "error: Azure OpenAI auth failed"
        if r.status_code == 429:
            return "error: Azure OpenAI rate limited"
        if r.status_code >= 400:
            return f"error: Azure OpenAI HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except Exception as e:
        return f"error: Azure OpenAI request failed: {e}"

    items = data.get("data") or []
    if not items:
        return "error: no embedding in Azure response"
    vec = items[0].get("embedding") or []
    return json.dumps({
        "model": f"azure/{deployment}",
        "dim": len(vec),
        "tokens": data.get("usage", {}).get("total_tokens", 0),
        "embedding": vec,
    })
