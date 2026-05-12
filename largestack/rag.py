"""Public RAG convenience API."""
from __future__ import annotations
from largestack._rag.pipeline import RAGPipeline
from largestack._rag.chunker import Chunker
from largestack._rag.retriever import HybridRetriever
from largestack._rag.embedder import Embedder
from largestack._rag.reranker import Reranker

def create_rag(documents: list[str] = None, chunk_size: int = 512, top_k: int = 5) -> RAGPipeline:
    """Create a RAG pipeline with sensible defaults."""
    return RAGPipeline(documents=documents, chunk_size=chunk_size, top_k=top_k)
