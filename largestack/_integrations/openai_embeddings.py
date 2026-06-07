"""OpenAI Embeddings integration — generate vector embeddings.

Auth: env var ``LARGESTACK_OPENAI_API_KEY`` (same key used for chat).

Used directly as a tool, but more typically called from RAG pipelines.
This is a thin wrapper that returns embeddings as a JSON-encoded list
of floats — agents can consume it for similarity search, clustering, etc.
"""

from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.embeddings")
_OPENAI_API = "https://api.openai.com/v1"


@tool(timeout=30)
async def openai_embed(text: str, model: str = "text-embedding-3-small") -> str:
    """Generate an embedding vector for the given text.

    Args:
        text: Input text. Max ~8K tokens for text-embedding-3-small.
        model: ``text-embedding-3-small`` (default, 1536-dim, cheap) or
            ``text-embedding-3-large`` (3072-dim, more accurate).

    Returns:
        JSON-encoded ``{"model": ..., "dim": ..., "embedding": [floats], "tokens": N}``,
        or error string.

    Requires: LARGESTACK_OPENAI_API_KEY env var.
    """
    key = os.environ.get("LARGESTACK_OPENAI_API_KEY", "").strip()
    if not key:
        return "Error: LARGESTACK_OPENAI_API_KEY env var not set."
    if not text or not isinstance(text, str):
        return "Error: text must be a non-empty string."
    if len(text) > 32000:
        return "Error: text too long (>32KB). Chunk it first."

    if model not in ("text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"):
        return (
            f"Error: unknown model {model!r}. Use text-embedding-3-small or text-embedding-3-large."
        )

    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(
            f"{_OPENAI_API}/embeddings",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"input": text, "model": model},
        )
    if r.status_code == 401:
        return "OpenAI auth failed. Check LARGESTACK_OPENAI_API_KEY."
    if r.status_code == 429:
        return "OpenAI rate limited. Retry after backoff."
    if r.status_code >= 400:
        return f"OpenAI API error: HTTP {r.status_code}: {r.text[:200]}"

    try:
        body = r.json()
        emb = body["data"][0]["embedding"]
        usage = body.get("usage", {})
    except (KeyError, IndexError, ValueError) as e:
        return f"OpenAI returned malformed response: {e}"

    return json.dumps(
        {
            "model": model,
            "dim": len(emb),
            "embedding": emb,
            "tokens": usage.get("total_tokens", 0),
        }
    )
