"""Semantic memory — similarity-based fact/knowledge recall.

Stores facts as vectors and recalls by similarity. NOTE: with no ``embedder``
supplied (the default, e.g. ``create_memory("semantic")``), it uses a 128-dim
bag-of-words HASH vector — i.e. token-overlap similarity, NOT true semantic
embeddings, so paraphrases won't match. Pass a real ``embedder`` (e.g. an
OpenAI/SentenceTransformer embed fn) for genuine semantic recall.
"""

from __future__ import annotations
import hashlib, logging, math, time
from typing import Any, Callable

log = logging.getLogger("largestack.memory.semantic")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticMemory:
    """Vector-based memory with similarity retrieval.

    mem = SemanticMemory(embedder=my_embedder)
    await mem.add("Python was created by Guido van Rossum in 1989")
    await mem.add("JavaScript was created by Brendan Eich in 1995")

    results = await mem.search("Who created Python?", k=1)
    # Returns the Python fact
    """

    def __init__(
        self, embedder: Callable = None, max_entries: int = 10000, similarity_threshold: float = 0.0
    ):
        self.embedder = embedder
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self._entries: list[dict] = []  # [{id, content, embedding, metadata, timestamp}]

    def _hash_id(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _embed(self, text: str) -> list[float]:
        if self.embedder is None:
            # Fallback: simple bag-of-words hash vector (deterministic)
            import hashlib

            words = text.lower().split()
            dim = 128
            vec = [0.0] * dim
            for w in words:
                h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
                vec[h % dim] += 1.0
            # Normalize
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            return [v / norm for v in vec]

        if hasattr(self.embedder, "__call__"):
            result = self.embedder(text)
            if hasattr(result, "__await__"):
                result = await result
            return result
        return self.embedder

    async def add(self, content: str, description: str = None, metadata: dict = None) -> str:
        """Add entry. Supports add(content, metadata=...) or add(key, description)."""
        # Legacy signature: add(key, description)
        if description is not None:
            md = dict(metadata or {})
            md["key"] = content
            md["description"] = description
            content = f"{content}: {description}"
            metadata = md

        if not content.strip():
            raise ValueError("Cannot add empty content")

        entry_id = self._hash_id(content)

        # Dedupe
        if any(e["id"] == entry_id for e in self._entries):
            log.debug(f"Semantic: entry {entry_id} already exists")
            return entry_id

        embedding = await self._embed(content)
        self._entries.append(
            {
                "id": entry_id,
                "content": content,
                "embedding": embedding,
                "metadata": metadata or {},
                "timestamp": time.time(),
            }
        )

        # Evict oldest if over limit
        if len(self._entries) > self.max_entries:
            self._entries = sorted(self._entries, key=lambda e: e["timestamp"])[-self.max_entries :]

        return entry_id

    async def search(self, query: str, k: int = 5, min_similarity: float = None) -> list[dict]:
        """Find k most similar entries. Returns list of {content, score, metadata}."""
        if not self._entries:
            return []

        query_emb = await self._embed(query)
        threshold = min_similarity if min_similarity is not None else self.similarity_threshold

        scored = []
        for e in self._entries:
            score = cosine_similarity(query_emb, e["embedding"])
            if score >= threshold:
                scored.append(
                    {
                        "content": e["content"],
                        "score": score,
                        "metadata": e["metadata"],
                        "id": e["id"],
                        "timestamp": e["timestamp"],
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    async def get(self, entry_id_or_key: str) -> dict | None:
        """Get entry by ID or by key (legacy)."""
        for e in self._entries:
            if e["id"] == entry_id_or_key:
                return {
                    "content": e["content"],
                    "metadata": e["metadata"],
                    "timestamp": e["timestamp"],
                    "description": e["metadata"].get("description", ""),
                }
            # Legacy key-based lookup
            if e["metadata"].get("key") == entry_id_or_key:
                return {
                    "content": e["content"],
                    "metadata": e["metadata"],
                    "timestamp": e["timestamp"],
                    "description": e["metadata"].get("description", e["content"]),
                }
        return None

    async def delete(self, entry_id: str) -> bool:
        for i, e in enumerate(self._entries):
            if e["id"] == entry_id:
                del self._entries[i]
                return True
        return False

    async def clear(self):
        self._entries = []

    @property
    def stats(self) -> dict:
        return {
            "entry_count": len(self._entries),
            "max_entries": self.max_entries,
            "has_embedder": self.embedder is not None,
        }

    def __len__(self):
        return len(self._entries)
