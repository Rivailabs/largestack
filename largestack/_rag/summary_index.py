"""Document Summary Index + Tree Summarize (v0.9.0).

Two advanced RAG patterns from LlamaIndex's playbook:

1. **DocumentSummaryIndex** — store per-document summaries plus chunks.
   At query time, embed the query, find the most relevant DOCUMENT (via
   summary), then retrieve detailed chunks only from that document.
   Beats naive chunk-level retrieval when documents are long and
   topically coherent (legal docs, papers, reports).

2. **TreeSummarize** — recursively summarize chunks bottom-up. Builds
   a hierarchy: leaf chunks → mid summaries → root summary. Lets you
   answer "what's this document about?" with O(log N) LLM calls instead
   of O(N).
"""
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("largestack.rag.summary_index")


# -------------------- Document Summary Index --------------------

@dataclass
class DocumentEntry:
    """One document in the summary index."""
    doc_id: str
    summary: str
    summary_embedding: list[float] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DocumentSummaryIndex:
    """Per-document summaries for hierarchical retrieval.

    Workflow:
    1. ``add_document(doc_id, full_text, chunks, summarizer_agent, embedder)``
       generates a summary, embeds it, stores everything.
    2. ``query(query, embedder, top_docs=2, top_chunks=5)`` returns
       chunks from the top-N most-relevant documents.
    """

    def __init__(self):
        self._docs: dict[str, DocumentEntry] = {}

    async def add_document(
        self,
        doc_id: str,
        full_text: str,
        chunks: list[dict],
        *,
        summarizer_agent,
        embedder: Callable[[str], "list[float] | str"],
        metadata: dict | None = None,
        max_summary_chars: int = 1000,
    ) -> None:
        """Add a document with auto-generated summary."""
        # Generate summary via LLM
        summary_prompt = (
            f"Summarize the following document in 1-3 paragraphs. "
            f"Focus on what topics it covers, not the full content.\n\n"
            f"{full_text[:8000]}"
        )
        try:
            resp = await summarizer_agent.run(summary_prompt)
            summary = (getattr(resp, "content", "") or "").strip()
            if len(summary) > max_summary_chars:
                summary = summary[:max_summary_chars]
        except Exception as e:
            log.warning(f"summary generation failed for {doc_id}: {e}")
            summary = full_text[:max_summary_chars]

        # Embed the summary
        try:
            emb_result = await embedder(summary)
            if isinstance(emb_result, str):
                # Tool-style return: JSON
                try:
                    emb_data = json.loads(emb_result)
                    embedding = emb_data.get("embedding", [])
                except json.JSONDecodeError:
                    embedding = []
            elif isinstance(emb_result, list):
                embedding = emb_result
            else:
                embedding = []
        except Exception as e:
            log.warning(f"summary embed failed for {doc_id}: {e}")
            embedding = []

        self._docs[doc_id] = DocumentEntry(
            doc_id=doc_id, summary=summary,
            summary_embedding=embedding, chunks=list(chunks),
            metadata=metadata or {},
        )

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        try:
            import math
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            if na == 0 or nb == 0:
                return 0.0
            return dot / (na * nb)
        except Exception:
            return 0.0

    async def query(
        self,
        query: str,
        *,
        embedder: Callable,
        top_docs: int = 2,
        top_chunks_per_doc: int = 5,
    ) -> list[dict]:
        """Find chunks from the most-relevant documents."""
        if not self._docs:
            return []

        # Embed query
        try:
            emb_result = await embedder(query)
            if isinstance(emb_result, str):
                emb_data = json.loads(emb_result)
                q_emb = emb_data.get("embedding", [])
            elif isinstance(emb_result, list):
                q_emb = emb_result
            else:
                q_emb = []
        except Exception:
            return []

        if not q_emb:
            return []

        # Score each doc by summary similarity
        scored = []
        for doc_id, entry in self._docs.items():
            score = self._cosine(q_emb, entry.summary_embedding)
            scored.append((score, doc_id, entry))
        scored.sort(reverse=True)

        # Pull chunks from top docs
        out = []
        for score, doc_id, entry in scored[:top_docs]:
            for i, chunk in enumerate(entry.chunks[:top_chunks_per_doc]):
                c = dict(chunk)
                c["doc_id"] = doc_id
                c["doc_score"] = score
                c["chunk_index"] = i
                out.append(c)
        return out

    def get_summaries(self) -> list[dict]:
        """List all stored doc summaries."""
        return [
            {
                "doc_id": d.doc_id,
                "summary": d.summary,
                "n_chunks": len(d.chunks),
                "metadata": d.metadata,
            }
            for d in self._docs.values()
        ]


# -------------------- Tree Summarize --------------------

async def tree_summarize(
    chunks: list[str],
    *,
    summarizer_agent,
    branching_factor: int = 4,
    max_chars_per_summary: int = 2000,
    instruction: str = "Summarize the following text concisely:",
) -> str:
    """Recursively summarize chunks bottom-up into a single summary.

    Args:
        chunks: list of text chunks (already split into LLM-context-fitting size).
        summarizer_agent: LARGESTACK Agent to do per-level summarization.
        branching_factor: how many chunks to combine per summary call.
        max_chars_per_summary: cap on each level's summary length.
        instruction: the prompt instruction prepended to text.

    Returns:
        Single root summary string.

    The number of LLM calls is O(N) overall but depth is O(log N), so
    latency scales much better than naive concat-and-summarize for
    long documents.
    """
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0][:max_chars_per_summary]

    current = list(chunks)
    level = 0
    while len(current) > 1:
        level += 1
        next_level: list[str] = []
        # Group into batches of `branching_factor`
        for i in range(0, len(current), branching_factor):
            batch = current[i : i + branching_factor]
            combined = "\n\n---\n\n".join(batch)
            prompt = f"{instruction}\n\n{combined}"
            try:
                resp = await summarizer_agent.run(prompt)
                summary = (getattr(resp, "content", "") or "").strip()
                if len(summary) > max_chars_per_summary:
                    summary = summary[:max_chars_per_summary]
            except Exception as e:
                log.warning(f"tree_summarize level {level} failed: {e}")
                summary = combined[:max_chars_per_summary]
            next_level.append(summary)
        log.debug(f"tree_summarize level {level}: {len(current)} → {len(next_level)}")
        current = next_level

    return current[0]


# -------------------- Combined: tree-summarize over a doc --------------------

async def summarize_document(
    full_text: str,
    *,
    summarizer_agent,
    chunk_size: int = 2000,
    branching_factor: int = 4,
) -> str:
    """Convenience: chunk a long document and tree-summarize.

    Useful for generating ``DocumentSummaryIndex`` summaries of very long
    documents that don't fit in a single LLM context.
    """
    chunks = [full_text[i : i + chunk_size] for i in range(0, len(full_text), chunk_size)]
    return await tree_summarize(
        chunks,
        summarizer_agent=summarizer_agent,
        branching_factor=branching_factor,
    )
