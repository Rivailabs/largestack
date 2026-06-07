"""HuggingFace Inference API embeddings (v0.8.0).

Auth: ``LARGESTACK_HF_API_KEY`` (or ``HF_TOKEN``) env var.

Uses HuggingFace's serverless Inference API. Hundreds of embedding
models are accessible — most popular: ``sentence-transformers/*``,
``BAAI/bge-*``, ``intfloat/e5-*``, ``thenlper/gte-*``.

API: ``POST https://api-inference.huggingface.co/pipeline/feature-extraction/{model}``
Body: ``{"inputs": "text", "options": {"wait_for_model": true}}``
Response: list of floats (1D for single input).

Note: HF serverless has cold-start latency (~5-30s for unused models)
and rate limits on the free tier. For production, use HF Inference
Endpoints (paid, dedicated).
"""

from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.hf_embed")
_HF_BASE = "https://api-inference.huggingface.co/pipeline/feature-extraction"

# Sanity-allowlist of common embedding models (used to validate input).
# Users may pass any model name — we don't HARD-restrict.
_KNOWN_PREFIXES = (
    "sentence-transformers/",
    "BAAI/bge-",
    "intfloat/e5-",
    "thenlper/gte-",
    "mixedbread-ai/",
    "Snowflake/",
    "nomic-ai/",
    "jinaai/",
)


@tool(timeout=60)  # HF cold starts can be slow
async def hf_embed(
    text: str,
    model: str = "sentence-transformers/all-MiniLM-L6-v2",
    wait_for_model: bool = True,
) -> str:
    """Generate an embedding via HuggingFace Inference API.

    Args:
        text: input text. Cap at ~32K characters per call.
        model: any HF model identifier supporting feature-extraction.
            Default ``sentence-transformers/all-MiniLM-L6-v2`` (384-dim,
            fast, good for general English).
        wait_for_model: if True, HF will wait for cold-loading models
            instead of returning 503 immediately.

    Returns:
        JSON string with: ``{"model", "dim", "embedding"}``
        OR a plain error string (does not raise so the agent loop survives).
    """
    api_key = (
        os.environ.get("LARGESTACK_HF_API_KEY")
        or os.environ.get("HF_TOKEN", "")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")
    )
    if not api_key:
        return "error: LARGESTACK_HF_API_KEY (or HF_TOKEN) not set"
    if not text or not isinstance(text, str):
        return "error: text must be a non-empty string"
    if len(text) > 32_000:
        return "error: text too long (>32K chars)"
    if not model or not isinstance(model, str):
        return "error: model must be a non-empty string"

    url = f"{_HF_BASE}/{model}"
    body: dict = {"inputs": text}
    if wait_for_model:
        body["options"] = {"wait_for_model": True}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if r.status_code == 401:
            return "error: HuggingFace auth failed (check LARGESTACK_HF_API_KEY)"
        if r.status_code == 429:
            return "error: HuggingFace rate limited"
        if r.status_code == 503:
            return f"error: HuggingFace model {model!r} loading (try wait_for_model=True)"
        if r.status_code >= 400:
            return f"error: HuggingFace HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.TimeoutException:
        return "error: HuggingFace request timed out"
    except Exception as e:
        return f"error: HuggingFace request failed: {e}"

    # Response shape: a list of floats (single input), or list of lists,
    # or list of list of floats (some models return per-token vectors).
    vec = _normalize_embedding(data)
    if vec is None:
        return "error: malformed HuggingFace response shape"

    return json.dumps(
        {
            "model": model,
            "dim": len(vec),
            "embedding": vec,
        }
    )


def _normalize_embedding(data) -> list[float] | None:
    """Coerce HF's many possible response shapes to a flat float list."""
    if isinstance(data, list):
        if not data:
            return None
        # Single embedding: list of floats
        if all(isinstance(x, (int, float)) for x in data):
            return [float(x) for x in data]
        # Wrapped: list of one list of floats
        if isinstance(data[0], list):
            inner = data[0]
            if all(isinstance(x, (int, float)) for x in inner):
                return [float(x) for x in inner]
            # Per-token vectors: take mean (typical for non-pooled outputs)
            if isinstance(inner[0], list) and all(isinstance(x, (int, float)) for x in inner[0]):
                # Mean-pool across tokens
                n_tokens = len(inner)
                dim = len(inner[0])
                return [sum(inner[t][d] for t in range(n_tokens)) / n_tokens for d in range(dim)]
    return None
