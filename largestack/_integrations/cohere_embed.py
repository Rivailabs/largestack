"""Cohere Embeddings integration (v0.7.0).

Auth: env var ``LARGESTACK_COHERE_API_KEY`` (or pass via the existing
LARGESTACK Cohere chat key — same key works for both endpoints).

Cohere Embed v4 supports:
- Multilingual semantic search
- Output dimensions: 256, 512, 1024 (default), 1536 (Matryoshka)
- input_type: ``search_document`` (default) or ``search_query``
- Up to 96 texts per batch, ~128K total tokens

API ref: https://docs.cohere.com/reference/embed
"""
from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.cohere_embed")
_COHERE_API = "https://api.cohere.com/v2/embed"

# Allowed Matryoshka output dimensions for embed-v4
_VALID_DIMS = {256, 512, 1024, 1536}
# Models supported (current as of April 2026)
_VALID_MODELS = {
    "embed-v4.0",
    "embed-english-v3.0",
    "embed-multilingual-v3.0",
    "embed-english-light-v3.0",
    "embed-multilingual-light-v3.0",
}


@tool(timeout=30)
async def cohere_embed(
    text: str,
    model: str = "embed-v4.0",
    input_type: str = "search_document",
    output_dimension: int = 1024,
) -> str:
    """Generate a Cohere embedding vector for the given text.

    Args:
        text: Input text. Cap at ~32K characters per call.
        model: ``embed-v4.0`` (default, multilingual, multimodal) or
            v3 family. See _VALID_MODELS for full list.
        input_type: ``search_document`` for indexing, ``search_query``
            for retrieval queries, ``classification``, or ``clustering``.
        output_dimension: 256/512/1024/1536 — Matryoshka truncation
            (only embed-v4 supports). Smaller = cheaper storage, slightly
            less accurate.

    Returns:
        JSON string with: ``{"model", "dim", "tokens", "embedding"}``
        OR a plain error string (does not raise so the agent loop survives).
    """
    api_key = (
        os.environ.get("LARGESTACK_COHERE_API_KEY")
        or os.environ.get("COHERE_API_KEY", "")
    )
    if not api_key:
        return "error: LARGESTACK_COHERE_API_KEY (or COHERE_API_KEY) not set"
    if not text or not isinstance(text, str):
        return "error: text must be a non-empty string"
    if len(text) > 32_000:
        return "error: text too long (>32K chars)"
    if model not in _VALID_MODELS:
        return f"error: unknown model {model!r}; valid: {sorted(_VALID_MODELS)}"
    if model == "embed-v4.0" and output_dimension not in _VALID_DIMS:
        return f"error: output_dimension must be one of {sorted(_VALID_DIMS)}"

    body: dict = {
        "model": model,
        "texts": [text],
        "input_type": input_type,
        "embedding_types": ["float"],
    }
    if model == "embed-v4.0":
        body["output_dimension"] = output_dimension

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _COHERE_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if r.status_code == 401:
            return "error: Cohere auth failed (check LARGESTACK_COHERE_API_KEY)"
        if r.status_code == 429:
            return "error: Cohere rate limited"
        if r.status_code >= 400:
            return f"error: Cohere HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.TimeoutException:
        return "error: Cohere request timed out"
    except Exception as e:
        return f"error: Cohere request failed: {e}"

    try:
        # v2 API returns { embeddings: { float: [[...]] } } structure
        embeddings = data.get("embeddings", {})
        if isinstance(embeddings, dict):
            float_embeds = embeddings.get("float", [])
        else:
            # Older v1-shaped response (just in case)
            float_embeds = embeddings
        if not float_embeds:
            return f"error: no embedding returned: {data}"
        vec = float_embeds[0]
        billed_units = data.get("meta", {}).get("billed_units", {})
        tokens = billed_units.get("input_tokens", 0)
    except (KeyError, IndexError, TypeError) as e:
        return f"error: malformed Cohere response: {e}"

    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": tokens,
        "embedding": vec,
    })
