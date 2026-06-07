"""Hybrid retrieval: BM25 + dense vector + Reciprocal Rank Fusion."""

from __future__ import annotations
import math, re
import logging
from collections import Counter, defaultdict

_log = logging.getLogger("largestack.rag")
from typing import Any


class BM25:
    """Okapi BM25 implementation for keyword search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.doc_freqs: dict[str, int] = Counter()
        self.avg_dl = 0.0

    def index(self, documents: list[str]):
        self.docs = [self._tokenize(d) for d in documents]
        self.avg_dl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        for doc in self.docs:
            seen = set()
            for term in doc:
                if term not in seen:
                    self.doc_freqs[term] += 1
                    seen.add(term)

    def search(self, query: str, top_k: int = 50) -> list[tuple[int, float]]:
        q_terms = self._tokenize(query)
        scores = []
        n = len(self.docs)
        for i, doc in enumerate(self.docs):
            score = 0.0
            dl = len(doc)
            tf_map = Counter(doc)
            for t in q_terms:
                if t not in tf_map:
                    continue
                tf = tf_map[t]
                df = self.doc_freqs.get(t, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
                tf_norm = (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
                )
                score += idf * tf_norm
            if score > 0:
                scores.append((i, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]

    @staticmethod
    def _stem(w: str) -> str:
        """Conservative suffix stemmer so 'Refunds'/'refund', 'programming'/'program'
        match without an external dependency. Not full Porter — handles the common
        plural/verb endings that otherwise break BM25 keyword overlap."""
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 4 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("ed"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        # collapse a doubled trailing consonant left by -ing/-ed (programm -> program)
        if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
            w = w[:-1]
        return w

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        return [cls._stem(t) for t in re.findall(r"\b\w+\b", text.lower())]


def rrf_fusion(
    results_lists: list[list[tuple[int, float]]], k: int = 60
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion — combine multiple ranked lists."""
    scores: dict[int, float] = defaultdict(float)
    for results in results_lists:
        for rank, (doc_id, _) in enumerate(results):
            scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    """Hybrid BM25 + dense retrieval with RRF fusion.

    Pipeline: BM25 search + vector search → RRF fusion → top-K
    Dense search requires embeddings (added in setup).
    """

    def __init__(self, documents: list[str] = None, embed_fn=None):
        self.documents = documents or []
        self.bm25 = BM25()
        self._embeddings: list[list[float]] | None = None
        self._embed_fn = embed_fn
        if self.documents:
            self.bm25.index(self.documents)

    def add_documents(self, docs: list[str]):
        self.documents.extend(docs)
        self.bm25.index(self.documents)

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float, str]]:
        """Search using BM25 (+ dense if available). Returns (doc_idx, score, text).

        Warning: If no embeddings are set via set_embeddings(), only BM25 keyword
        search is used. Call set_embeddings() for true hybrid search.
        """
        bm25_results = self.bm25.search(query, top_k=50)

        # If embeddings available, also do dense search + RRF
        if self._embeddings:
            dense_results = self._dense_search(query, top_k=50)
            fused = rrf_fusion([bm25_results, dense_results])
        else:
            if not hasattr(self, "_warned_no_embeddings"):
                _log.warning(
                    "HybridRetriever: No embeddings set — using BM25-only. "
                    "Call set_embeddings() for dense+BM25 hybrid search."
                )
                self._warned_no_embeddings = True
            fused = bm25_results

        results = []
        for doc_id, score in fused[:top_k]:
            if doc_id < len(self.documents):
                results.append((doc_id, score, self.documents[doc_id]))
        return results

    def set_embeddings(self, embeddings: list[list[float]], embed_fn=None):
        """Set pre-computed embeddings for dense search."""
        self._embeddings = embeddings
        if embed_fn:
            self._embed_fn = embed_fn

    def _dense_search(self, query: str, top_k: int = 50) -> list[tuple[int, float]]:
        """Dense vector search via cosine similarity."""
        import math

        if not self._embeddings:
            return []
        # Embed query using same method
        if not self._embed_fn:
            return []
        result = self._embed_fn(query)
        # Handle both sync and async embed functions
        import asyncio, inspect

        if inspect.isawaitable(result) or asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures

                # Already in async context — run in thread
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    q_emb = loop.run_in_executor(pool, lambda: asyncio.run(self._embed_fn(query)))
                    _log.warning(
                        "HybridRetriever: embed_fn is async but called in async context — "
                        "falling back to BM25-only. Use a sync embed_fn for hybrid search."
                    )
                    return []
            except RuntimeError:
                q_emb = asyncio.run(result)
        else:
            q_emb = result
        if not q_emb:
            return []
        results = []
        for i, doc_emb in enumerate(self._embeddings):
            dot = sum(a * b for a, b in zip(q_emb, doc_emb))
            na = math.sqrt(sum(a * a for a in q_emb))
            nb = math.sqrt(sum(b * b for b in doc_emb))
            score = dot / (na * nb) if na > 0 and nb > 0 else 0
            results.append((i, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
