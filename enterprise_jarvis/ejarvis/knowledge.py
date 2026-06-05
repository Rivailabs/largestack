"""Tiny RAG: keyword retrieval over the local knowledge base, with citations.

Honest about what it is — keyword scoring, not a vector DB. Returns (source, snippet)
pairs so the agent can cite, and nothing when there's no relevant match.
"""
from __future__ import annotations

import re

from .config import KNOWLEDGE_DIR


def search(query: str, k: int = 2) -> list[tuple[str, str]]:
    words = {w for w in re.findall(r"[a-zA-Z]{3,}", query.lower())}
    if not words or not KNOWLEDGE_DIR.is_dir():
        return []
    scored: list[tuple[int, str, str]] = []
    for doc in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = doc.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        score = sum(low.count(w) for w in words)
        if score:
            # Return the most relevant paragraph as the snippet.
            paras = [p.strip() for p in text.split("\n\n") if p.strip()]
            best_para = max(paras, key=lambda p: sum(p.lower().count(w) for w in words)) if paras else text
            scored.append((score, doc.name, best_para[:400]))
    scored.sort(reverse=True)
    return [(src, snip) for _, src, snip in scored[:k]]
