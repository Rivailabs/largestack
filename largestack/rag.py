"""Public RAG convenience API."""

from __future__ import annotations
from largestack._rag.pipeline import RAGPipeline
from largestack._rag.chunker import Chunker
from largestack._rag.retriever import HybridRetriever
from largestack._rag.embedder import Embedder
from largestack._rag.reranker import Reranker


def create_rag(
    documents: list[str] = None,
    chunk_size: int = 512,
    top_k: int = 5,
    dense: bool = False,
    embed_fn=None,
    reranker=None,
) -> RAGPipeline:
    """Create a RAG pipeline.

    Defaults to BM25 keyword retrieval. Set ``dense=True`` (local
    sentence-transformers) or pass a sync ``embed_fn`` to enable hybrid BM25 +
    dense retrieval; pass a ``Reranker`` via ``reranker`` to enable reranking.
    """
    return RAGPipeline(
        documents=documents,
        chunk_size=chunk_size,
        top_k=top_k,
        dense=dense,
        embed_fn=embed_fn,
        reranker=reranker,
    )
