"""Embedding engine — production-grade with multiple backends and batching."""
from __future__ import annotations
import os, hashlib, logging, math
from typing import Any

log = logging.getLogger("largestack.embedder")


class Embedder:
    """Generate embeddings with multiple backends.
    
    Backends (auto-selected by priority):
      1. 'openai'  — text-embedding-3-small/large (requires LARGESTACK_OPENAI_API_KEY)
      2. 'voyage'  — voyage-3-large (requires LARGESTACK_VOYAGE_API_KEY)
      3. 'cohere'  — embed-v3 (requires LARGESTACK_COHERE_API_KEY)
      4. 'local'   — sentence-transformers all-MiniLM-L6-v2 (pip install sentence-transformers)
      5. 'mock'    — deterministic hash-based (for testing only)
    
    Features:
      - Batch API calls (100× faster for large corpora)
      - LRU cache with configurable size
      - Dimension truncation for OpenAI v3 models
      - Graceful fallback chain
    
        e = Embedder(backend="auto", dim=512)
        vec = await e.embed("hello world")
        vecs = await e.embed_batch(["text1", "text2", "text3"])
    """
    
    # Known model dimensions
    MODEL_DIMS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        "voyage-3-large": 1024,
        "voyage-3": 1024,
        "voyage-code-3": 1024,
        "embed-english-v3.0": 1024,
        "embed-multilingual-v3.0": 1024,
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
    }
    
    def __init__(self, backend: str = "auto", model: str = "text-embedding-3-small",
                 dim: int = None, cache: bool = True, cache_size: int = 10000,
                 batch_size: int = 100):
        self.backend = backend
        self.model = model
        self.dim = dim  # Optional: truncate to this dimension
        self.batch_size = batch_size
        self._cache: dict[str, list[float]] = {} if cache else None
        self._cache_size = cache_size
        self._local_model = None  # Lazy-loaded sentence-transformer
        self._resolved_backend = None
    
    def _resolve_backend(self) -> str:
        """Determine which backend to use based on available credentials."""
        if self._resolved_backend: return self._resolved_backend
        if self.backend != "auto":
            self._resolved_backend = self.backend
            return self.backend
        
        # Priority: OpenAI > Voyage > Cohere > local > mock
        if os.environ.get("LARGESTACK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            self._resolved_backend = "openai"
        elif os.environ.get("LARGESTACK_VOYAGE_API_KEY") or os.environ.get("VOYAGE_API_KEY"):
            self._resolved_backend = "voyage"
            if "voyage" not in self.model: self.model = "voyage-3"
        elif os.environ.get("LARGESTACK_COHERE_API_KEY") or os.environ.get("COHERE_API_KEY"):
            self._resolved_backend = "cohere"
            if "embed" not in self.model: self.model = "embed-english-v3.0"
        else:
            # Try local sentence-transformers
            try:
                from sentence_transformers import SentenceTransformer
                self._resolved_backend = "local"
                if not self.model.startswith("all-"): self.model = "all-MiniLM-L6-v2"
            except Exception:
                # B-03 (v0.3.4): Fail loud — mock is dangerous in production.
                # In production: hard-fail. In dev: require explicit opt-in.
                env = os.environ.get("LARGESTACK_ENV", "development").lower()
                allow_mock = os.environ.get("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "").lower() in ("1", "true", "yes")
                if env == "production":
                    raise ImportError(
                        "Embedder: no API keys (OPENAI/VOYAGE/COHERE) and sentence-transformers "
                        "not installed. Mock embeddings are not allowed in production. "
                        "Install: pip install largestack[rag] OR set OPENAI_API_KEY."
                    )
                if not allow_mock:
                    raise ImportError(
                        "Embedder: no API keys and sentence-transformers not installed. "
                        "Mock embeddings would produce semantically meaningless results. "
                        "Either install sentence-transformers (`pip install largestack[rag]`), "
                        "set OPENAI_API_KEY, or set LARGESTACK_ALLOW_MOCK_EMBEDDINGS=1 to opt into "
                        "deterministic-but-meaningless mock embeddings (development only)."
                    )
                self._resolved_backend = "mock"
                log.warning(
                    "Embedder: USING MOCK EMBEDDINGS (LARGESTACK_ALLOW_MOCK_EMBEDDINGS=1). "
                    "Vector search will return semantically meaningless results. "
                    "Install sentence-transformers for real local embeddings."
                )
        
        log.info(f"Embedder: backend={self._resolved_backend}, model={self.model}")
        return self._resolved_backend
    
    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}::{text}".encode()).hexdigest()
    
    def _cache_put(self, key: str, value: list[float]):
        if self._cache is None: return
        # LRU eviction: if over size, drop oldest
        if len(self._cache) >= self._cache_size:
            # Remove oldest ~10% (simple FIFO)
            to_remove = list(self._cache.keys())[:self._cache_size // 10]
            for k in to_remove: del self._cache[k]
        self._cache[key] = value
    
    def _truncate(self, emb: list[float]) -> list[float]:
        """Truncate to self.dim dimensions (only valid for OpenAI v3 models)."""
        if self.dim and len(emb) > self.dim:
            # Renormalize after truncation (OpenAI v3 supports Matryoshka)
            truncated = emb[:self.dim]
            norm = math.sqrt(sum(v*v for v in truncated))
            return [v/norm for v in truncated] if norm > 0 else truncated
        return emb
    
    async def embed(self, text: str) -> list[float]:
        """Embed a single text."""
        if not text or not text.strip():
            dim = self.dim or self.MODEL_DIMS.get(self.model, 128)
            return [0.0] * dim
        
        # Check cache
        key = self._cache_key(text) if self._cache is not None else None
        if key and key in self._cache:
            return self._cache[key]
        
        backend = self._resolve_backend()
        try:
            if backend == "openai":
                emb = await self._openai_embed([text])
                emb = emb[0]
            elif backend == "voyage":
                emb = await self._voyage_embed([text])
                emb = emb[0]
            elif backend == "cohere":
                emb = await self._cohere_embed([text])
                emb = emb[0]
            elif backend == "local":
                emb = self._local_embed(text)
            else:
                emb = self._mock_embed(text)
        except Exception as e:
            # v0.3.6: do NOT silently fall back to mock after a real backend failure.
            # In production: re-raise. In dev: re-raise unless explicit opt-in.
            env = os.environ.get("LARGESTACK_ENV", "development").lower()
            allow = os.environ.get("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "").lower() in ("1", "true", "yes")
            if env == "production" or backend == "mock" or not allow:
                log.error(f"Embedder {backend} failed: {e}. Refusing to fall back to mock.")
                raise
            log.warning(
                f"Embedder {backend} failed: {e}. Falling back to mock "
                f"(LARGESTACK_ALLOW_MOCK_EMBEDDINGS=1; dev only)."
            )
            emb = self._mock_embed(text)
        
        emb = self._truncate(emb)
        if key: self._cache_put(key, emb)
        return emb
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts with batched API calls (much faster)."""
        if not texts: return []
        
        # Check cache for each
        results = [None] * len(texts)
        to_embed = []
        to_embed_idx = []
        
        if self._cache is not None:
            for i, t in enumerate(texts):
                key = self._cache_key(t)
                if key in self._cache:
                    results[i] = self._cache[key]
                else:
                    to_embed.append(t)
                    to_embed_idx.append(i)
        else:
            to_embed = list(texts)
            to_embed_idx = list(range(len(texts)))
        
        if not to_embed:
            return results
        
        backend = self._resolve_backend()
        new_embeddings: list[list[float]] = []
        
        try:
            # Batch API calls
            if backend == "openai":
                for i in range(0, len(to_embed), self.batch_size):
                    batch = to_embed[i:i + self.batch_size]
                    new_embeddings.extend(await self._openai_embed(batch))
            elif backend == "voyage":
                for i in range(0, len(to_embed), self.batch_size):
                    batch = to_embed[i:i + self.batch_size]
                    new_embeddings.extend(await self._voyage_embed(batch))
            elif backend == "cohere":
                for i in range(0, len(to_embed), self.batch_size):
                    batch = to_embed[i:i + self.batch_size]
                    new_embeddings.extend(await self._cohere_embed(batch))
            elif backend == "local":
                new_embeddings = [self._local_embed(t) for t in to_embed]
            else:
                new_embeddings = [self._mock_embed(t) for t in to_embed]
        except Exception as e:
            # v0.3.6: production never falls back to mock after a real backend failure.
            env = os.environ.get("LARGESTACK_ENV", "development").lower()
            allow = os.environ.get("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "").lower() in ("1", "true", "yes")
            if env == "production" or backend == "mock" or not allow:
                log.error(f"Batch embed failed ({backend}): {e}. Refusing to fall back to mock.")
                raise
            log.warning(
                f"Batch embed failed ({backend}): {e}. Falling back to mock "
                f"(LARGESTACK_ALLOW_MOCK_EMBEDDINGS=1; dev only)."
            )
            new_embeddings = [self._mock_embed(t) for t in to_embed]
        
        # Truncate + cache + fill results
        for idx, emb in zip(to_embed_idx, new_embeddings):
            emb = self._truncate(emb)
            results[idx] = emb
            if self._cache is not None:
                self._cache_put(self._cache_key(texts[idx]), emb)
        
        return results
    
    async def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        key = os.environ.get("LARGESTACK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        payload = {"input": [t[:8000] for t in texts], "model": self.model}
        if self.dim and self.model.startswith("text-embedding-3"):
            payload["dimensions"] = self.dim
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}"}, json=payload)
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
    
    async def _voyage_embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        key = os.environ.get("LARGESTACK_VOYAGE_API_KEY") or os.environ.get("VOYAGE_API_KEY", "")
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={"input": texts, "model": self.model})
            r.raise_for_status()
            return [d["embedding"] for d in r.json()["data"]]
    
    async def _cohere_embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        key = os.environ.get("LARGESTACK_COHERE_API_KEY") or os.environ.get("COHERE_API_KEY", "")
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.cohere.com/v1/embed",
                headers={"Authorization": f"Bearer {key}"},
                json={"texts": texts, "model": self.model, "input_type": "search_document"})
            r.raise_for_status()
            return r.json()["embeddings"]
    
    def _local_embed(self, text: str) -> list[float]:
        """Local sentence-transformers inference."""
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.model)
        return self._local_model.encode(text, convert_to_numpy=True).tolist()
    
    def _mock_embed(self, text: str, dim: int | None = None) -> list[float]:
        """Deterministic hash-based embedding. TOKEN-FREQUENCY aware, not random."""
        # Generate directly at requested dimension so Matryoshka-style truncation
        # cannot accidentally cut away every non-zero mock dimension.
        dim = dim or self.dim or 128
        words = text.lower().split()
        if not words:
            return [0.0] * dim

        vec = [0.0] * dim
        for w in words:
            h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
            # Distribute word across several dimensions (not just one)
            for off in range(3):
                idx = (h >> (off * 21)) % dim
                vec[idx] += 1.0
        
        # Normalize to unit vector
        norm = math.sqrt(sum(v*v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec
