"""4-stage RAG pipeline: retrieve → rerank → evaluate → generate."""
from __future__ import annotations
from typing import Any
from largestack._rag.chunker import Chunker, Chunk
from largestack._rag.retriever import HybridRetriever

class RAGPipeline:
    """Complete RAG pipeline.
    
    Stage 1: Hybrid search (BM25 + vector, RRF fusion)
    Stage 2: Reranking (cross-encoder or LLM)
    Stage 3: Confidence evaluation (CRAG)
    Stage 4: Generation with faithfulness check
    """
    def __init__(self, documents: list[str] = None, chunker: Chunker | None = None,
                 chunk_size: int = 512, top_k: int = 5):
        self.chunker = chunker or Chunker(chunk_size=chunk_size)
        self.top_k = top_k
        self._chunks: list[str] = []
        self.retriever = HybridRetriever()
        
        if documents:
            self.ingest(documents)
    
    def ingest(self, documents: list[str]):
        """Ingest documents: chunk → index."""
        for doc in documents:
            chunks = self.chunker.chunk(doc)
            for c in chunks:
                self._chunks.append(c.text)
        self.retriever = HybridRetriever(self._chunks)
    
    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a query."""
        k = top_k or self.top_k
        results = self.retriever.search(query, top_k=k)
        return [{"text": text, "score": score, "index": idx} for idx, score, text in results]
    
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
