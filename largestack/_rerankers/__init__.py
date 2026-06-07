"""Rerankers — re-order retrieval results for relevance (v0.8.0).

Two rerankers shipped:

1. **Cohere Rerank v3.5** — production-grade rerank API. Sends
   ``(query, [doc1, doc2, ...])`` and returns docs re-ordered by a
   purpose-trained relevance model.

2. **RankGPT** — uses an LLM to rerank. Slower and more expensive,
   but works with any LLM provider (no extra API key) and often
   outperforms Cohere on domain-specific text.

Both follow the same signature::

    async def rerank(
        query: str,
        documents: list[dict],   # must have "content" or be plain strings
        *,
        top_k: int = 5,
    ) -> list[dict]

Returned dicts have the original fields plus ``rerank_score``.
"""

from __future__ import annotations
import json
import logging
import os
import re
from typing import Any

import httpx

log = logging.getLogger("largestack.rerankers")

_COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"


def _doc_text(d: Any) -> str:
    """Extract text from doc dict or accept plain string."""
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        return d.get("content", "") or d.get("text", "") or ""
    return str(d)


# -------------------- Cohere Rerank --------------------


async def cohere_rerank(
    query: str,
    documents: list[Any],
    *,
    top_k: int = 5,
    model: str = "rerank-v3.5",
    api_key: str | None = None,
    timeout: float = 30.0,
) -> list[dict]:
    """Rerank documents via Cohere Rerank API.

    Args:
        query: search query.
        documents: list of dicts (with ``content``) or plain strings.
        top_k: number of results to return.
        model: Cohere rerank model (``rerank-v3.5`` is current 2026 default).
        api_key: override; else reads ``LARGESTACK_COHERE_API_KEY`` or
            ``COHERE_API_KEY``.
        timeout: HTTP timeout in seconds.

    Returns:
        List of original docs (or {"content": str} if input was plain
        strings) re-ordered by ``rerank_score``, capped at ``top_k``.

    Notes:
        - Returns original list ordering if API fails (graceful degradation).
        - Cohere Rerank v3.5 supports up to 1000 documents per call,
          context length up to 4096 tokens per doc.
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    if not documents:
        return []

    key = (
        api_key
        or os.environ.get("LARGESTACK_COHERE_API_KEY")
        or os.environ.get("COHERE_API_KEY", "")
    )
    if not key:
        log.warning("cohere_rerank: no API key, falling back to original order")
        # Wrap strings as dicts so output shape is consistent
        normalized = [d if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents]
        return normalized[:top_k]

    # Build doc texts
    doc_texts = [_doc_text(d) for d in documents]

    body = {
        "model": model,
        "query": query,
        "documents": doc_texts,
        "top_n": min(top_k, len(documents)),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                _COHERE_RERANK_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if r.status_code >= 400:
            log.warning(f"cohere_rerank HTTP {r.status_code}: {r.text[:200]}")
            normalized = [
                d if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents
            ]
            return normalized[:top_k]
        data = r.json()
    except Exception as e:
        log.warning(f"cohere_rerank failed: {e}")
        normalized = [d if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents]
        return normalized[:top_k]

    results = data.get("results") or []
    out: list[dict] = []
    for r_item in results:
        idx = r_item.get("index", -1)
        score = float(r_item.get("relevance_score", 0.0))
        if 0 <= idx < len(documents):
            orig = documents[idx]
            doc = dict(orig) if isinstance(orig, dict) else {"content": _doc_text(orig)}
            doc["rerank_score"] = score
            out.append(doc)
    return out[:top_k]


# -------------------- RankGPT --------------------

RANKGPT_PROMPT = """You are RankGPT, an intelligent assistant that can \
rank passages based on their relevance to the query.

I will provide you with {n} passages, each indicated by a number identifier \
[]. Rank them based on their relevance to query: "{query}"

{passages}

Search Query: {query}

Rank the {n} passages above based on their relevance to the search query. \
The most relevant passage should be ranked first. Output ONLY the ranking \
results as a comma-separated list of identifiers, e.g. "[3] > [1] > [4] > [2]". \
Output ONLY the ranking, nothing else."""


async def rankgpt_rerank(
    query: str,
    documents: list[Any],
    *,
    agent,
    top_k: int = 5,
    max_doc_chars: int = 1500,
) -> list[dict]:
    """Rerank documents using an LLM (RankGPT pattern).

    Args:
        query: search query.
        documents: list of dicts (with ``content``) or plain strings.
        agent: a LARGESTACK Agent (or anything with ``run(task)`` method).
        top_k: number to return after ranking.
        max_doc_chars: truncate each doc to this many chars before
            sending to the LLM (saves tokens).

    Returns:
        List of original dicts (or wrapped strings) re-ordered by LLM
        ranking, capped at ``top_k``. Falls back to original order if
        LLM output can't be parsed.

    Reference: Sun et al. "Is ChatGPT Good at Search? Investigating
    Large Language Models as Re-Ranking Agent" (EMNLP 2023).
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    if not documents:
        return []

    n = len(documents)
    # Build numbered passages
    passages_lines = []
    for i, d in enumerate(documents, 1):
        text = _doc_text(d)
        if len(text) > max_doc_chars:
            text = text[:max_doc_chars] + "..."
        passages_lines.append(f"[{i}] {text}")
    passages = "\n\n".join(passages_lines)

    prompt = RANKGPT_PROMPT.format(n=n, query=query, passages=passages)

    try:
        result = await agent.run(prompt, max_turns=1)
        text = getattr(result, "content", "") or ""
    except Exception as e:
        log.warning(f"rankgpt_rerank LLM failed: {e}")
        normalized = [d if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents]
        return normalized[:top_k]

    # Parse ranking — accept "[3] > [1] > [4]" or "3, 1, 4" or "3 > 1 > 4"
    ids_in_order = re.findall(r"\[?(\d+)\]?", text)
    seen: set = set()
    ordered_indices: list[int] = []
    for s in ids_in_order:
        try:
            idx = int(s) - 1  # 1-indexed → 0-indexed
        except ValueError:
            continue
        if 0 <= idx < n and idx not in seen:
            seen.add(idx)
            ordered_indices.append(idx)

    # Append any indices the LLM forgot, preserving original order
    for i in range(n):
        if i not in seen:
            ordered_indices.append(i)

    out: list[dict] = []
    for rank, idx in enumerate(ordered_indices[:top_k], start=1):
        orig = documents[idx]
        doc = dict(orig) if isinstance(orig, dict) else {"content": _doc_text(orig)}
        # Higher rank → higher score; normalize to (0, 1]
        doc["rerank_score"] = round(1.0 - (rank - 1) / max(1, top_k), 6)
        out.append(doc)
    return out


# -------------------- v0.9.0: 3 more rerankers --------------------


async def voyage_rerank(
    query: str,
    documents: list,
    *,
    top_k: int = 5,
    model: str = "rerank-2",
    api_key: str | None = None,
) -> list[dict]:
    """Voyage AI Rerank — production-grade reranker.

    Models:
    - ``rerank-2`` (default) — current best, multilingual
    - ``rerank-2-lite`` — faster, less accurate
    - ``rerank-1`` — legacy

    Auth: LARGESTACK_VOYAGE_API_KEY or VOYAGE_API_KEY env var.
    """
    if not documents:
        return []
    api_key = (
        api_key
        or os.environ.get("LARGESTACK_VOYAGE_API_KEY")
        or os.environ.get("VOYAGE_API_KEY", "")
    )
    if not api_key:
        log.debug("voyage_rerank: no API key, returning input unchanged")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    doc_texts = [_doc_text(d) for d in documents]
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.voyageai.com/v1/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "documents": doc_texts,
                    "model": model,
                    "top_k": top_k,
                },
            )
        if r.status_code != 200:
            log.warning(f"Voyage rerank HTTP {r.status_code}")
            return [
                dict(d) if isinstance(d, dict) else {"content": _doc_text(d)}
                for d in documents[:top_k]
            ]
        data = r.json()
    except Exception as e:
        log.warning(f"Voyage rerank failed: {e}")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    results = data.get("data", [])
    out = []
    for item in results[:top_k]:
        idx = item.get("index", 0)
        if 0 <= idx < len(documents):
            orig = documents[idx]
            doc = dict(orig) if isinstance(orig, dict) else {"content": _doc_text(orig)}
            doc["rerank_score"] = float(item.get("relevance_score", 0.0))
            out.append(doc)
    return out


async def jina_rerank(
    query: str,
    documents: list,
    *,
    top_k: int = 5,
    model: str = "jina-reranker-v2-base-multilingual",
    api_key: str | None = None,
) -> list[dict]:
    """Jina AI Rerank — multilingual reranker.

    Models:
    - ``jina-reranker-v2-base-multilingual`` (default)
    - ``jina-reranker-v1-base-en``
    - ``jina-reranker-v1-turbo-en`` — faster

    Auth: LARGESTACK_JINA_API_KEY or JINA_API_KEY env var.
    """
    if not documents:
        return []
    api_key = (
        api_key or os.environ.get("LARGESTACK_JINA_API_KEY") or os.environ.get("JINA_API_KEY", "")
    )
    if not api_key:
        log.debug("jina_rerank: no API key, returning input unchanged")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    doc_texts = [_doc_text(d) for d in documents]
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.jina.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "query": query,
                    "documents": doc_texts,
                    "top_n": top_k,
                },
            )
        if r.status_code != 200:
            log.warning(f"Jina rerank HTTP {r.status_code}")
            return [
                dict(d) if isinstance(d, dict) else {"content": _doc_text(d)}
                for d in documents[:top_k]
            ]
        data = r.json()
    except Exception as e:
        log.warning(f"Jina rerank failed: {e}")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    results = data.get("results", [])
    out = []
    for item in results[:top_k]:
        idx = item.get("index", 0)
        if 0 <= idx < len(documents):
            orig = documents[idx]
            doc = dict(orig) if isinstance(orig, dict) else {"content": _doc_text(orig)}
            doc["rerank_score"] = float(item.get("relevance_score", 0.0))
            out.append(doc)
    return out


# Local cross-encoder (no API key, no network)
_CE_MODELS: dict = {}


async def cross_encoder_rerank(
    query: str,
    documents: list,
    *,
    top_k: int = 5,
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> list[dict]:
    """Cross-encoder reranker using sentence-transformers (local).

    Popular models:
    - ``cross-encoder/ms-marco-MiniLM-L-6-v2`` — default, fast
    - ``cross-encoder/ms-marco-MiniLM-L-12-v2`` — more accurate, slower
    - ``BAAI/bge-reranker-large`` — multilingual

    Requires: ``pip install sentence-transformers``.
    Runs locally — no API calls.
    """
    if not documents:
        return []
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        log.warning("cross_encoder_rerank: sentence-transformers not installed")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    try:
        if model not in _CE_MODELS:
            log.info(f"loading cross-encoder model: {model}")
            _CE_MODELS[model] = CrossEncoder(model)
        ce = _CE_MODELS[model]
    except Exception as e:
        log.warning(f"cross_encoder load failed: {e}")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    pairs = [(query, _doc_text(d)) for d in documents]
    try:
        import asyncio as _asyncio

        scores = await _asyncio.to_thread(ce.predict, pairs)
    except Exception as e:
        log.warning(f"cross_encoder predict failed: {e}")
        return [
            dict(d) if isinstance(d, dict) else {"content": _doc_text(d)} for d in documents[:top_k]
        ]

    indexed = sorted(
        enumerate(documents),
        key=lambda kv: float(scores[kv[0]]) if kv[0] < len(scores) else 0.0,
        reverse=True,
    )
    out = []
    for orig_idx, orig in indexed[:top_k]:
        doc = dict(orig) if isinstance(orig, dict) else {"content": _doc_text(orig)}
        doc["rerank_score"] = float(scores[orig_idx])
        out.append(doc)
    return out
