"""End-to-end RAG example.

Demonstrates the simplest possible production RAG pipeline:
1. Load some text documents
2. Chunk + embed them with a deterministic local demo embedder
3. Store in an in-memory vector store
4. Answer queries with citation

Run::

    python rag_basic.py

For a real deployment, replace the deterministic demo embedder with a provider
embedder and switch `MemoryVectorStore` to `PgVectorStore` or Qdrant.
"""

from __future__ import annotations
import asyncio
import hashlib

from largestack._rag.vector_store import InMemoryVectorStore
from largestack._core.citation_sandbox import CitationEngine


SAMPLE_DOCS = [
    {
        "id": "doc1",
        "content": (
            "Largestack AI is an open-source agent framework built for "
            "Indian fintech and legaltech. It provides DPDP-compliant PII "
            "redaction, hash-chain audit logs, and per-tenant rate-limiting."
        ),
    },
    {
        "id": "doc2",
        "content": (
            "Razorpay is the leading payment gateway in India. LARGESTACK ships a "
            "first-class RazorpayToolkit with payment links, refunds, and "
            "subscription management."
        ),
    },
    {
        "id": "doc3",
        "content": (
            "Aadhaar OKYC requires partner credentials from Signzy or IDfy. "
            "LARGESTACK automatically masks Aadhaar numbers in logs as "
            "'XXXX XXXX 1234' format to comply with UIDAI regulations."
        ),
    },
]


def demo_embed(text: str, dim: int = 64) -> list[float]:
    """Small deterministic embedding for an offline documentation example."""
    digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
    raw = (digest * ((dim // len(digest)) + 1))[:dim]
    return [(byte / 255.0) for byte in raw]


async def embed_and_index(store: InMemoryVectorStore, docs: list[dict]) -> None:
    """Embed each doc and upsert into the vector store."""
    for doc in docs:
        await store.add(doc["id"], demo_embed(doc["content"]), {"content": doc["content"]})


async def query(
    store: InMemoryVectorStore,
    question: str,
    top_k: int = 3,
) -> list[dict]:
    """Retrieve top-k relevant docs."""
    return await store.search(demo_embed(question), top_k=top_k)


async def main():
    print("Building index from 3 sample documents...")
    store = InMemoryVectorStore(dim=64)
    await embed_and_index(store, SAMPLE_DOCS)
    print(f"  ✓ Indexed {len(SAMPLE_DOCS)} documents")

    question = "How does LARGESTACK handle Aadhaar privacy?"
    print(f"\nQuery: {question}")
    results = await query(store, question, top_k=2)

    print(f"\nTop {len(results)} results:")
    for i, r in enumerate(results, 1):
        content_preview = r["content"][:120]
        print(f"  [{i}] score={r['score']:.3f}  {content_preview}...")

    # Generate citations
    print("\nWith citations:")
    docs_for_cite = [{"id": r["id"], "content": r["content"]} for r in results]
    answer = (
        "LARGESTACK automatically masks Aadhaar numbers in logs to comply with UIDAI regulations."
    )
    cited = CitationEngine().cite(answer, docs_for_cite)
    print(f"  {cited.text_with_citations}")
    print("\nSources:")
    for src in cited.sources:
        print(f"  [{src['n']}] {src['id']}: {src['content_preview'][:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
