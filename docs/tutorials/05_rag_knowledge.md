# Tutorial 5: RAG and Knowledge Bases

Give your agent access to your documents.

## Quick RAG Pipeline

```python
from largestack import Agent, create_rag

# Ingest documents
rag = create_rag(
    documents=[
        "Largestack AI costs $299 per year for production deployment.",
        "The framework supports 13 LLM providers.",
        "Steering hooks provide programmatic control over agent behavior.",
    ],
    chunk_size=512,
    top_k=3,
)

# Convert to agent tool
search_tool = rag.as_tool()

agent = Agent(
    name="knowledge-agent",
    instructions="Always search the knowledge base before answering.",
    tools=[search_tool],
    llm="openai/gpt-4o-mini",
)

result = await agent.run("How much does LARGESTACK cost?")
```

## How It Works

1. **Chunking** — documents split into 512-token chunks (5 strategies: recursive, sentence, paragraph, heading, fixed)
2. **Indexing** — BM25 keyword index built automatically
3. **Retrieval** — BM25 search + optional dense vector search + RRF fusion
4. **Reranking** — keyword bigram scorer (or cross-encoder model)
5. **CRAG** — confidence evaluation decides: use results / combine with web / fall back to web

## Hybrid Search (BM25 + Dense)

```python
from largestack._rag import RAGPipeline, Embedder

rag = RAGPipeline(documents=docs)

# Add embeddings for dense search
embedder = Embedder(backend="openai")  # or "mock" for testing
embeddings = await embedder.embed_batch([chunk.text for chunk in rag._chunks])
rag.retriever.set_embeddings(embeddings, embed_fn=embedder._mock_embed)
```

## Graph RAG

```python
from largestack._rag.graph_rag import GraphRAG

graph = GraphRAG()
await graph.ingest(["Python is used in AI and machine learning..."])
answer = await graph.query("What is Python used for?")
```
