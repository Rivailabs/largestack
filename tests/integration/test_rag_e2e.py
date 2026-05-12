"""RAG integration tests — no API key needed."""
import asyncio, sys
sys.path.insert(0, ".")

def test_rag_ingest_and_retrieve():
    from largestack._rag.pipeline import RAGPipeline
    docs = [
        "Largestack AI is a universal agentic framework costing 299 dollars per year.",
        "The framework supports 13 LLM providers including OpenAI and Anthropic.",
        "Steering hooks achieve 100 percent accuracy compared to 82 percent for prompts.",
    ]
    rag = RAGPipeline(documents=docs, chunk_size=200)
    results = rag.retrieve("pricing cost 299 dollars")
    assert any("299" in r["text"] for r in results)

def test_rag_with_embeddings():
    from largestack._rag.retriever import HybridRetriever
    from largestack._rag.embedder import Embedder
    
    docs = ["Python is great for AI", "Java is enterprise", "Rust is fast"]
    retriever = HybridRetriever(docs)
    
    # Set mock embeddings
    import asyncio
    emb = Embedder(backend="mock")
    embeddings = asyncio.run(emb.embed_batch(docs))
    # Use mock embedder's sync method directly
    retriever.set_embeddings(embeddings, embed_fn=lambda q: emb._mock_embed(q))
    
    results = retriever.search("Python artificial intelligence", top_k=2)
    assert len(results) > 0

def test_rag_as_tool():
    from largestack._rag.pipeline import RAGPipeline
    rag = RAGPipeline(documents=["Test content here."])
    tool_fn = rag.as_tool()
    assert hasattr(tool_fn, "_is_largestack_tool") and tool_fn._is_largestack_tool
    result = asyncio.run(tool_fn(query="test content"))
    assert "Test" in result

def test_reranker_improves_order():
    from largestack._rag.reranker import Reranker
    docs = [
        {"text": "Java enterprise patterns and frameworks", "score": 0.9},
        {"text": "Python machine learning and data science", "score": 0.8},
        {"text": "Rust systems programming for performance", "score": 0.7},
    ]
    reranked = Reranker().rerank("Python data science machine learning", docs)
    assert "Python" in reranked[0]["text"]
