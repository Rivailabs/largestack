"""Semantic cache — cache similar queries using embedding similarity."""

from __future__ import annotations
import hashlib, json, time, math
from typing import Any


class SemanticCache:
    """3-tier semantic cache: exact hash → semantic similarity → miss.

    Exact: SHA-256 hash match (0ms overhead)
    Semantic: cosine similarity >= threshold (10-50ms)
    Supports max_size limit with LRU eviction and per-entry TTL.
    """

    def __init__(self, max_size: int = 1000, ttl: int = 3600, similarity_threshold: float = 0.92):
        self._exact: dict[str, dict] = {}
        self._semantic: list[dict] = []  # [{embedding, response, timestamp}]
        self.max_size = max_size
        self.ttl = ttl
        self.threshold = similarity_threshold

    def get_exact(self, messages: list[dict], model: str, **kw) -> dict | None:
        """Tier 1: Exact hash match. Behavior-affecting params included in key."""
        key = self._hash(messages, model, **kw)
        entry = self._exact.get(key)
        if entry and time.time() - entry["ts"] < self.ttl:
            entry["last_access"] = time.time()
            return entry["response"]
        return None

    def get_semantic(self, query_embedding: list[float]) -> dict | None:
        """Tier 2: Semantic similarity match."""
        if not query_embedding or not self._semantic:
            return None
        best_score = 0.0
        best_entry = None
        for entry in self._semantic:
            if time.time() - entry["ts"] > self.ttl:
                continue
            score = self._cosine(query_embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_score >= self.threshold and best_entry:
            return best_entry["response"]
        return None

    def put_exact(self, messages: list[dict], model: str, response: dict, **kw):
        """Store exact match. Behavior-affecting params included in key."""
        if len(self._exact) >= self.max_size:
            oldest = min(
                self._exact, key=lambda k: self._exact[k].get("last_access", self._exact[k]["ts"])
            )
            del self._exact[oldest]
        self._exact[self._hash(messages, model, **kw)] = {
            "response": response,
            "ts": time.time(),
            "last_access": time.time(),
        }

    def put_semantic(self, embedding: list[float], response: dict):
        """Store semantic entry."""
        if len(self._semantic) >= self.max_size:
            self._semantic.pop(0)
        self._semantic.append({"embedding": embedding, "response": response, "ts": time.time()})

    def clear(self):
        self._exact.clear()
        self._semantic.clear()

    @property
    def stats(self) -> dict:
        return {"exact_entries": len(self._exact), "semantic_entries": len(self._semantic)}

    @staticmethod
    def _hash(messages: list[dict], model: str, **kw) -> str:
        # P1: include behavior-affecting params (tools, temperature, max_tokens, structured params, tool_choice)
        key_data = {
            "m": messages,
            "model": model,
            "tools": kw.get("tools"),
            "temperature": kw.get("temperature"),
            "max_tokens": kw.get("max_tokens"),
            "response_format": kw.get("response_format"),
            "tool_choice": kw.get("tool_choice"),
            "top_p": kw.get("top_p"),
            "seed": kw.get("seed"),
        }
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True, default=str).encode()
        ).hexdigest()

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
