"""Cross-encoder reranker for RAG precision — multi-backend with caching.

Backends:
  - keyword: TF-IDF + n-gram overlap (no external deps)
  - cross_encoder: bge-reranker-v2-m3 (local, requires sentence-transformers)
  - cohere: Cohere Rerank 3.5 (API, high accuracy)
  - voyage: Voyage AI Rerank-2 (API, high accuracy)
  - custom: User-provided callable
"""

from __future__ import annotations
import hashlib, logging, math, os, re
from collections import Counter
from typing import Any, Callable

log = logging.getLogger("largestack.reranker")


class Reranker:
    """Rerank RAG retrieval results by relevance to query.

    The reranker improves precision after broad retrieval — typical pipeline:
      1. Fast retrieval: BM25 + dense → 50 candidates
      2. Reranker: Pick top 5 most relevant

        # Local (no API, no dependencies)
        r = Reranker(mode="keyword")

        # Cross-encoder local model
        r = Reranker(mode="cross_encoder")

        # Cohere API
        r = Reranker(mode="cohere", model="rerank-v3.5")

        # Usage
        ranked = r.rerank("user query", docs, top_k=5)
    """

    MODES = ("keyword", "cross_encoder", "cohere", "voyage", "custom")

    def __init__(
        self,
        mode: str = "keyword",
        model: str = None,
        cache: bool = True,
        min_score: float = 0.0,
        custom_fn: Callable = None,
    ):
        if mode not in self.MODES:
            raise ValueError(f"mode must be in {self.MODES}")
        self.mode = mode
        self.min_score = min_score
        self._encoder = None
        self._cache: dict = {} if cache else None
        self.custom_fn = custom_fn

        # Default models per mode
        self.model = model or {
            "cross_encoder": "BAAI/bge-reranker-v2-m3",
            "cohere": "rerank-v3.5",
            "voyage": "rerank-2",
        }.get(mode, "")

    def _cache_key(self, query: str, doc_text: str) -> str:
        return hashlib.sha256(
            f"{self.mode}::{self.model}::{query}::{doc_text[:200]}".encode()
        ).hexdigest()

    def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        """Rerank documents by relevance to query.

        Args:
          query: Search query string
          documents: list of {"text": str, ...} dicts
          top_k: Number to return

        Returns:
          Top-k documents with "rerank_score" added, sorted by score desc
        """
        if not documents:
            return []
        if top_k <= 0:
            return []

        if self.mode == "custom" and self.custom_fn:
            return self._rerank_custom(query, documents, top_k)

        if self.mode == "cross_encoder":
            return self._rerank_cross_encoder(query, documents, top_k)

        if self.mode == "cohere":
            return self._rerank_cohere(query, documents, top_k)

        if self.mode == "voyage":
            return self._rerank_voyage(query, documents, top_k)

        # Default: keyword
        return self._rerank_keyword(query, documents, top_k)

    def _rerank_keyword(self, query: str, documents: list[dict], top_k: int) -> list[dict]:
        """TF-IDF + n-gram keyword-based reranking."""
        # Preprocess
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return documents[:top_k]

        q_set = set(q_tokens)
        q_bigrams = set(zip(q_tokens, q_tokens[1:]))
        q_trigrams = set(zip(q_tokens, q_tokens[1:], q_tokens[2:]))

        # Compute DF for IDF scoring
        df = Counter()
        doc_tokens_cache = []
        for doc in documents:
            tokens = self._tokenize(doc.get("text", ""))
            doc_tokens_cache.append(tokens)
            for t in set(tokens):
                df[t] += 1

        N = len(documents)
        scored = []
        for doc, tokens in zip(documents, doc_tokens_cache):
            if not tokens:
                scored.append({**doc, "rerank_score": 0.0})
                continue

            d_set = set(tokens)
            d_bigrams = set(zip(tokens, tokens[1:]))
            d_trigrams = set(zip(tokens, tokens[1:], tokens[2:]))

            # Unigram TF-IDF
            uni_score = 0.0
            for t in q_set & d_set:
                tf = tokens.count(t) / len(tokens)
                idf = math.log(N / (df[t] + 1)) + 1
                uni_score += tf * idf

            # Bigram overlap (phrase match bonus)
            bi_score = len(q_bigrams & d_bigrams) / max(len(q_bigrams), 1) if q_bigrams else 0

            # Trigram overlap (exact phrase bonus)
            tri_score = len(q_trigrams & d_trigrams) / max(len(q_trigrams), 1) if q_trigrams else 0

            # Weighted combination
            score = 0.5 * min(uni_score, 1.0) + 0.3 * bi_score + 0.2 * tri_score
            scored.append({**doc, "rerank_score": score})

        # Filter min_score + sort + top_k
        scored = [d for d in scored if d["rerank_score"] >= self.min_score]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "of",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "and",
            "or",
            "but",
        }
        tokens = re.findall(r"\b[a-z]+\b", text.lower())
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def _rerank_cross_encoder(self, query: str, documents: list[dict], top_k: int) -> list[dict]:
        """Local cross-encoder model reranking."""
        try:
            from sentence_transformers import CrossEncoder

            if not self._encoder:
                self._encoder = CrossEncoder(self.model)
                log.info(f"Reranker: loaded cross-encoder {self.model}")
            pairs = [(query, doc.get("text", "")) for doc in documents]
            scores = self._encoder.predict(pairs)
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = float(score)
            documents = [d for d in documents if d["rerank_score"] >= self.min_score]
            documents.sort(key=lambda x: x["rerank_score"], reverse=True)
            return documents[:top_k]
        except ImportError:
            log.warning("sentence-transformers not installed — falling back to keyword")
            return self._rerank_keyword(query, documents, top_k)
        except Exception as e:
            log.error(f"Cross-encoder rerank failed: {e}")
            return self._rerank_keyword(query, documents, top_k)

    def _rerank_cohere(self, query: str, documents: list[dict], top_k: int) -> list[dict]:
        """Cohere Rerank API."""
        try:
            import httpx

            key = os.environ.get("LARGESTACK_COHERE_API_KEY") or os.environ.get("COHERE_API_KEY")
            if not key:
                log.warning("No Cohere API key — falling back to keyword")
                return self._rerank_keyword(query, documents, top_k)

            texts = [doc.get("text", "") for doc in documents]
            # Sync call (httpx.Client, not async)
            with httpx.Client(timeout=30) as c:
                r = c.post(
                    "https://api.cohere.com/v2/rerank",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": texts,
                        "top_n": top_k,
                    },
                )
                r.raise_for_status()
                results = r.json()["results"]

            reranked = []
            for item in results:
                doc = dict(documents[item["index"]])
                doc["rerank_score"] = item["relevance_score"]
                if doc["rerank_score"] >= self.min_score:
                    reranked.append(doc)
            return reranked
        except Exception as e:
            log.error(f"Cohere rerank failed: {e}")
            return self._rerank_keyword(query, documents, top_k)

    def _rerank_voyage(self, query: str, documents: list[dict], top_k: int) -> list[dict]:
        """Voyage AI Rerank API."""
        try:
            import httpx

            key = os.environ.get("LARGESTACK_VOYAGE_API_KEY") or os.environ.get("VOYAGE_API_KEY")
            if not key:
                log.warning("No Voyage API key — falling back to keyword")
                return self._rerank_keyword(query, documents, top_k)

            texts = [doc.get("text", "") for doc in documents]
            with httpx.Client(timeout=30) as c:
                r = c.post(
                    "https://api.voyageai.com/v1/rerank",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": texts,
                        "top_k": top_k,
                    },
                )
                r.raise_for_status()
                results = r.json()["data"]

            reranked = []
            for item in results:
                doc = dict(documents[item["index"]])
                doc["rerank_score"] = item["relevance_score"]
                if doc["rerank_score"] >= self.min_score:
                    reranked.append(doc)
            return reranked
        except Exception as e:
            log.error(f"Voyage rerank failed: {e}")
            return self._rerank_keyword(query, documents, top_k)

    def _rerank_custom(self, query: str, documents: list[dict], top_k: int) -> list[dict]:
        """User-provided reranker function."""
        try:
            scored = self.custom_fn(query, documents)
            if not isinstance(scored, list):
                raise ValueError("custom_fn must return list of docs")
            return scored[:top_k]
        except Exception as e:
            log.error(f"Custom reranker failed: {e}")
            return documents[:top_k]

    @property
    def stats(self) -> dict:
        return {
            "mode": self.mode,
            "model": self.model,
            "min_score": self.min_score,
            "cache_size": len(self._cache) if self._cache is not None else 0,
        }
