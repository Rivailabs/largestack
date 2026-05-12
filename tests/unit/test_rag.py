"""Tests for RAG engine."""
import asyncio
from largestack._rag.chunker import Chunker
from largestack._rag.retriever import HybridRetriever, BM25, rrf_fusion
from largestack._rag.pipeline import RAGPipeline
from largestack._rag.embedder import Embedder
from largestack._rag.reranker import Reranker
from largestack._rag.crag import CRAGEvaluator
from largestack._rag.graph_rag import GraphRAG
from largestack._rag.vector_store import InMemoryVectorStore

def test_chunker_recursive():
    c = Chunker(chunk_size=50)
    chunks = c.chunk("First sentence here. Second sentence here. Third sentence is longer than expected.")
    assert len(chunks) >= 1

def test_chunker_sentence():
    c = Chunker(strategy="sentence", chunk_size=100)
    chunks = c.chunk("Hello world. How are you. Fine thanks. Goodbye now.")
    assert all(len(ch.text) <= 120 for ch in chunks)

def test_bm25():
    bm25 = BM25()
    bm25.index(["python programming language", "java enterprise framework", "rust systems programming"])
    results = bm25.search("python programming")
    assert results[0][0] == 0  # First doc should rank highest

def test_rrf():
    list1 = [(0, 0.9), (1, 0.8), (2, 0.7)]
    list2 = [(2, 0.95), (0, 0.85), (1, 0.5)]
    fused = rrf_fusion([list1, list2])
    assert len(fused) == 3

def test_hybrid_retriever():
    r = HybridRetriever(["Machine learning uses Python", "Java is enterprise", "Rust is fast"])
    results = r.search("Python machine learning", top_k=2)
    assert len(results) > 0 and "Python" in results[0][2]

def test_pipeline():
    rag = RAGPipeline(documents=["LARGESTACK costs 299 per year.", "LARGESTACK supports 15 providers."])
    ctx = rag.build_context("299 cost year")
    assert "299" in ctx

def test_pipeline_as_tool():
    rag = RAGPipeline(documents=["Test document content."])
    tool_fn = rag.as_tool()
    assert tool_fn._is_largestack_tool

def test_embedder_mock():
    e = Embedder(backend="mock")
    emb = asyncio.run(e.embed("test query"))
    assert len(emb) == 128
    norm = sum(v*v for v in emb) ** 0.5
    assert abs(norm - 1.0) < 0.01  # Normalized

def test_reranker():
    r = Reranker()
    docs = [{"text": "python programming"}, {"text": "java enterprise"}, {"text": "python machine learning"}]
    ranked = r.rerank("python", docs, top_k=2)
    assert "python" in ranked[0]["text"].lower()

def test_crag():
    c = CRAGEvaluator()
    assert c.evaluate("q", [{"score": 0.9}])["action"] == "proceed"
    assert c.evaluate("q", [{"score": 0.5}])["action"] == "combine"
    assert c.evaluate("q", [{"score": 0.1}])["action"] == "web_search"
    assert c.evaluate("q", [])["action"] == "web_search"

def test_graph_rag():
    g = GraphRAG()
    asyncio.run(g.ingest(["Python is used in Machine Learning and Data Science."]))
    assert len(g.graph) > 0

def test_vector_store():
    v = InMemoryVectorStore(dim=3)
    asyncio.run(v.add("a", [1,0,0], {"t": "x"}))
    asyncio.run(v.add("b", [0,1,0], {"t": "y"}))
    r = asyncio.run(v.search([0.9, 0.1, 0], top_k=1))
    assert r[0]["id"] == "a"
