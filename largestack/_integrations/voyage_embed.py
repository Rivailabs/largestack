"""Voyage AI Embeddings integration (v0.7.0).

Auth: env var ``LARGESTACK_VOYAGE_API_KEY`` (or ``VOYAGE_API_KEY``).

Voyage embeddings (voyage-3.5, voyage-3-large, voyage-code-3, etc.) are
known for top retrieval benchmarks. Specialized models for code, legal,
finance domains.

API ref: https://docs.voyageai.com/reference/embeddings-api
"""

from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.voyage_embed")
_VOYAGE_API = "https://api.voyageai.com/v1/embeddings"

# Models supported (current as of April 2026)
_VALID_MODELS = {
    "voyage-3.5",
    "voyage-3.5-lite",
    "voyage-3-large",
    "voyage-code-3",
    "voyage-finance-2",
    "voyage-law-2",
    "voyage-multilingual-2",
    "voyage-large-2-instruct",
    "voyage-multimodal-3",
    "voyage-context-3",
}
# Matryoshka dimension support varies by model
_DIM_SUPPORTED = {
    "voyage-3-large",
    "voyage-3.5",
    "voyage-3.5-lite",
    "voyage-code-3",
    "voyage-4-large",
    "voyage-4",
    "voyage-4-lite",
}
_VALID_DIMS = {256, 512, 1024, 2048}


@tool(timeout=30)
async def voyage_embed(
    text: str,
    model: str = "voyage-3.5",
    input_type: str | None = None,
    output_dimension: int | None = None,
) -> str:
    """Generate a Voyage embedding vector for the given text.

    Args:
        text: Input text. Cap at ~32K characters per call.
        model: ``voyage-3.5`` (default, multilingual general purpose),
            ``voyage-3.5-lite`` (cheaper), ``voyage-code-3`` (code RAG),
            ``voyage-law-2`` (legal docs), ``voyage-finance-2``, etc.
        input_type: Optional. ``query`` for search queries,
            ``document`` for indexed content. Voyage prepends the
            appropriate prompt automatically. None = no prepending.
        output_dimension: For Matryoshka models — 256/512/1024/2048.
            Default is None (model's default).

    Returns:
        JSON string with: ``{"model", "dim", "tokens", "embedding"}``
        OR a plain error string (does not raise so the agent loop survives).
    """
    api_key = os.environ.get("LARGESTACK_VOYAGE_API_KEY") or os.environ.get("VOYAGE_API_KEY", "")
    if not api_key:
        return "error: LARGESTACK_VOYAGE_API_KEY (or VOYAGE_API_KEY) not set"
    if not text or not isinstance(text, str):
        return "error: text must be a non-empty string"
    if len(text) > 32_000:
        return "error: text too long (>32K chars)"
    if model not in _VALID_MODELS:
        return f"error: unknown model {model!r}; valid: {sorted(_VALID_MODELS)}"
    if input_type is not None and input_type not in {"query", "document"}:
        return "error: input_type must be None, 'query', or 'document'"
    if output_dimension is not None:
        if model not in _DIM_SUPPORTED:
            return f"error: model {model} doesn't support custom dimensions"
        if output_dimension not in _VALID_DIMS:
            return f"error: output_dimension must be one of {sorted(_VALID_DIMS)}"

    body: dict = {
        "model": model,
        "input": [text],
    }
    if input_type is not None:
        body["input_type"] = input_type
    if output_dimension is not None:
        body["output_dimension"] = output_dimension

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _VOYAGE_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if r.status_code == 401:
            return "error: Voyage auth failed (check LARGESTACK_VOYAGE_API_KEY)"
        if r.status_code == 429:
            return "error: Voyage rate limited"
        if r.status_code >= 400:
            return f"error: Voyage HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.TimeoutException:
        return "error: Voyage request timed out"
    except Exception as e:
        return f"error: Voyage request failed: {e}"

    try:
        items = data.get("data", [])
        if not items:
            return f"error: no embedding returned: {data}"
        vec = items[0].get("embedding") or []
        if not vec:
            return "error: empty embedding in response"
        tokens = data.get("usage", {}).get("total_tokens", 0)
    except (KeyError, IndexError, TypeError) as e:
        return f"error: malformed Voyage response: {e}"

    return json.dumps(
        {
            "model": model,
            "dim": len(vec),
            "tokens": tokens,
            "embedding": vec,
        }
    )
