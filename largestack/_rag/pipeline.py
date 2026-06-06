"""RAG pipeline: retrieval (BM25, optionally + dense hybrid) with optional reranking."""
from __future__ import annotations
import logging
from typing import Any, Callable
from largestack._rag.chunker import Chunker, Chunk
from largestack._rag.retriever import HybridRetriever

_log = logging.getLogger("largestack.rag")


def default_local_embed_fn() -> Callable[[str], list[float]] | None:
    """Sync local embedder (sentence-transformers ``all-MiniLM-L6-v2``) for dense
    retrieval. Returns None if sentence-transformers isn't installed — the pipeline
    then stays BM25-only. Sync so it works inside the agent's async tool path."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        _log.warning("dense retrieval requested but sentence-transformers is not "
                     "installed (`pip install largestack[rag]`); using BM25-only.")
        return None
    model = SentenceTransformer("all-MiniLM-L6-v2")

    def _embed(text: str) -> list[float]:
        return [float(x) for x in model.encode(text)]
    return _embed


class RAGPipeline:
    """RAG pipeline.

    Stage 1 — retrieval: BM25 keyword search by default. Pass ``dense=True`` (uses
      a local sentence-transformers model) or your own sync ``embed_fn`` to enable
      **hybrid BM25 + dense vector search with RRF fusion**.
    Stage 2 — reranking: enabled when a ``Reranker`` is passed via ``reranker=``.
    Stages 3–4 (CRAG confidence, faithfulness) are available as separate composable
      components (``largestack._rag.crag.CRAGEvaluator``, ``largestack._rag.eval``);
      they are not auto-run by ``build_context()``.
    """
    def __init__(self, documents: list[str] = None, chunker: Chunker | None = None,
                 chunk_size: int = 512, top_k: int = 5,
                 embed_fn: Callable[[str], list[float]] | None = None,
                 dense: bool | str = False, reranker: Any = None):
        self.chunker = chunker or Chunker(chunk_size=chunk_size)
        self.top_k = top_k
        self._chunks: list[str] = []
        # Opt-in dense embeddings (default BM25-only keeps setup instant + offline).
        # dense=True or dense="auto" → use a local embedder when available (auto is a
        # no-op if sentence-transformers isn't installed; BM25 stays the fallback).
        _want_dense = dense is True or dense == "auto"
        self._embed_fn = embed_fn or (default_local_embed_fn() if _want_dense else None)
        self.reranker = reranker
        self.retriever = HybridRetriever()

        if documents:
            self.ingest(documents)

    def ingest(self, documents: list[str]):
        """Ingest documents: chunk → index (+ embed for dense search if enabled)."""
        for doc in documents:
            chunks = self.chunker.chunk(doc)
            for c in chunks:
                self._chunks.append(c.text)
        self.retriever = HybridRetriever(self._chunks)
        # Wire dense search when an embedder is configured (was never done before,
        # so "hybrid" silently degraded to BM25-only).
        if self._embed_fn and self._chunks:
            try:
                embeddings = [self._embed_fn(c) for c in self._chunks]
                self.retriever.set_embeddings(embeddings, embed_fn=self._embed_fn)
            except Exception as e:
                _log.warning("RAG dense embedding failed (%s); falling back to BM25-only.", e)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a query (rerank if a reranker is configured)."""
        k = top_k or self.top_k
        # Fetch a wider candidate set when reranking, then narrow to k.
        fetch = max(k, 50) if self.reranker else k
        results = self.retriever.search(query, top_k=fetch)
        docs = [{"text": text, "score": score, "index": idx} for idx, score, text in results]
        if self.reranker is not None:
            try:
                docs = self.reranker.rerank(query, docs, top_k=k)
            except Exception as e:
                _log.warning("RAG rerank failed (%s); returning retrieval order.", e)
                docs = docs[:k]
        return docs[:k]
    
    def build_context(self, query: str, top_k: int | None = None) -> str:
        """Build context string for LLM from retrieved chunks."""
        results = self.retrieve(query, top_k)
        if not results:
            return "No relevant information found."
        context_parts = []
        for i, r in enumerate(results):
            context_parts.append(f"[Source {i+1}] {r['text']}")
        return "\n\n".join(context_parts)
    
    def as_tool(self):
        """Convert RAG pipeline to a @tool for use in agents."""
        from largestack._core.tools import tool
        pipeline = self
        
        @tool
        async def search_knowledge(query: str) -> str:
            """Search the knowledge base for relevant information."""
            return pipeline.build_context(query)
        
        return search_knowledge
