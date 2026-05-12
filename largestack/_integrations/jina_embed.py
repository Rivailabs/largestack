"""Jina AI embeddings (v0.8.0).

Auth: ``LARGESTACK_JINA_API_KEY`` (or ``JINA_API_KEY``) env var.

Jina offers state-of-the-art multilingual embeddings:
- ``jina-embeddings-v3`` (default, 1024-dim, 89 languages, Matryoshka)
- ``jina-embeddings-v2-base-en`` (768-dim, English-only, faster)
- ``jina-clip-v1`` (multimodal — text + image)

API: ``POST https://api.jina.ai/v1/embeddings``
Format: OpenAI-compatible.
"""
from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.jina_embed")
_JINA_API = "https://api.jina.ai/v1/embeddings"

_VALID_TASKS = {
    "retrieval.query",
    "retrieval.passage",
    "separation",
    "classification",
    "text-matching",
}

# Models supported (current as of April 2026)
_VALID_MODELS = {
    "jina-embeddings-v3",
    "jina-embeddings-v2-base-en",
    "jina-embeddings-v2-base-de",
    "jina-embeddings-v2-base-es",
    "jina-embeddings-v2-base-zh",
    "jina-embeddings-v2-base-code",
    "jina-clip-v1",
    "jina-clip-v2",
}


@tool(timeout=30)
async def jina_embed(
    text: str,
    model: str = "jina-embeddings-v3",
    task: str | None = "retrieval.passage",
    output_dimension: int | None = None,
) -> str:
    """Generate a Jina embedding vector for the given text.

    Args:
        text: input text. Cap at ~32K characters per call.
        model: ``jina-embeddings-v3`` (default, multilingual) or v2 family.
        task: optional task hint that improves quality:
            ``retrieval.query`` for search queries,
            ``retrieval.passage`` (default) for indexed content,
            ``separation``, ``classification``, ``text-matching``.
            Only supported for ``jina-embeddings-v3``.
        output_dimension: Matryoshka dimension override (256-1024).
            Only supported for ``jina-embeddings-v3``.

    Returns:
        JSON string with: ``{"model", "dim", "tokens", "embedding"}``
        OR a plain error string.
    """
    api_key = (
        os.environ.get("LARGESTACK_JINA_API_KEY")
        or os.environ.get("JINA_API_KEY", "")
    )
    if not api_key:
        return "error: LARGESTACK_JINA_API_KEY (or JINA_API_KEY) not set"
    if not text or not isinstance(text, str):
        return "error: text must be a non-empty string"
    if len(text) > 32_000:
        return "error: text too long (>32K chars)"
    if model not in _VALID_MODELS:
        return f"error: unknown model {model!r}; valid: {sorted(_VALID_MODELS)}"
    if task is not None and task not in _VALID_TASKS:
        return f"error: invalid task {task!r}; valid: {sorted(_VALID_TASKS)}"
    if output_dimension is not None:
        if model != "jina-embeddings-v3":
            return f"error: output_dimension only supported on jina-embeddings-v3"
        if not (256 <= output_dimension <= 1024):
            return "error: output_dimension must be in [256, 1024]"

    body: dict = {
        "model": model,
        "input": [text],
    }
    if task and model == "jina-embeddings-v3":
        body["task"] = task
    if output_dimension is not None:
        body["dimensions"] = output_dimension

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _JINA_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if r.status_code == 401:
            return "error: Jina auth failed (check LARGESTACK_JINA_API_KEY)"
        if r.status_code == 429:
            return "error: Jina rate limited"
        if r.status_code >= 400:
            return f"error: Jina HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
    except httpx.TimeoutException:
        return "error: Jina request timed out"
    except Exception as e:
        return f"error: Jina request failed: {e}"

    try:
        items = data.get("data") or []
        if not items:
            return f"error: no embedding returned: {data}"
        vec = items[0].get("embedding") or []
        if not vec:
            return "error: empty embedding in response"
        tokens = (data.get("usage") or {}).get("total_tokens", 0)
    except (KeyError, IndexError, TypeError) as e:
        return f"error: malformed Jina response: {e}"

    return json.dumps({
        "model": model,
        "dim": len(vec),
        "tokens": tokens,
        "embedding": vec,
    })
