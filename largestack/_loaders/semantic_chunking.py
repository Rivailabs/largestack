"""Semantic chunking (v0.14.0).

Closes Tier A #13. Splits documents at semantic boundaries (paragraph
topic shifts) rather than fixed token counts.

Algorithm (LlamaIndex-inspired):

1. Split text into sentences (or pre-existing paragraphs)
2. Embed each sentence
3. Compute cosine distance between adjacent sentences
4. Insert chunk break wherever distance exceeds the configured threshold
5. Greedily concatenate sentences within ``max_chunk_chars`` and
   ``min_chunk_chars`` bounds

This catches topic shifts that fixed-size chunking misses. Especially
useful for legal/compliance docs where section boundaries don't align
with token counts.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Protocol

log = logging.getLogger("largestack.loaders.semantic")


# Pattern for sentence splitting — handles . ! ? ; … followed by space + caps
# Plus Indic Danda (।) for Hindi/Sanskrit text
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?।…])\s+(?=[A-Z\u0900-\u097F\u0980-\u09FF])"
    r"|(?<=[.!?।…])\s*$"
)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences (Latin + Indic Danda support)."""
    if not text or not text.strip():
        return []
    # Use simple split — pre-collapse newlines that could fool the regex
    normalized = re.sub(r"\s+", " ", text.strip())
    sentences = _SENTENCE_SPLIT.split(normalized)
    return [s.strip() for s in sentences if s.strip()]


class _EmbedProtocol(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class SemanticChunk:
    """One chunk produced by semantic splitting."""
    content: str
    sentence_indices: tuple[int, int]  # (start_inclusive, end_exclusive)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticChunker:
    """Embedding-based semantic chunker.

    Args:
        embedder: any object with async ``embed_batch`` method
        breakpoint_distance: insert a break when adjacent-sentence cosine
            distance ≥ this threshold (default 0.4 — empirically good
            for Indian legal text and English news articles)
        min_chunk_chars: don't emit chunks smaller than this — merge
            with the next sentence instead
        max_chunk_chars: force a break if a chunk grows beyond this
        sentences_per_window: average over N adjacent sentences for the
            distance computation (smooths noise in single-sentence
            embeddings)
    """
    embedder: Any
    breakpoint_distance: float = 0.4
    min_chunk_chars: int = 200
    max_chunk_chars: int = 4000
    sentences_per_window: int = 1

    def __post_init__(self):
        if not (0.0 <= self.breakpoint_distance <= 2.0):
            raise ValueError("breakpoint_distance must be in [0.0, 2.0]")
        if self.min_chunk_chars < 1:
            raise ValueError("min_chunk_chars must be ≥ 1")
        if self.max_chunk_chars < self.min_chunk_chars:
            raise ValueError(
                "max_chunk_chars must be ≥ min_chunk_chars"
            )
        if self.sentences_per_window < 1:
            raise ValueError("sentences_per_window must be ≥ 1")

    async def chunk(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> list[SemanticChunk]:
        """Produce semantic chunks for a single text input."""
        if not text or not text.strip():
            return []

        sentences = split_sentences(text)
        if not sentences:
            return []
        if len(sentences) == 1:
            return [SemanticChunk(
                content=sentences[0],
                sentence_indices=(0, 1),
                metadata=metadata or {},
            )]

        # Embed all sentences in one batch
        embeddings = await self.embedder.embed_batch(sentences)

        # Optional windowing for smoother distance signal
        if self.sentences_per_window > 1:
            window_embeds = self._average_windows(
                embeddings, self.sentences_per_window,
            )
        else:
            window_embeds = embeddings

        # Compute adjacent-sentence cosine distances
        distances: list[float] = []
        for i in range(len(window_embeds) - 1):
            sim = _cosine(window_embeds[i], window_embeds[i + 1])
            distances.append(1.0 - sim)  # distance = 1 - similarity

        # Find breakpoints
        breakpoints: list[int] = []
        for idx, d in enumerate(distances):
            if d >= self.breakpoint_distance:
                breakpoints.append(idx + 1)  # break BEFORE this sentence

        # Build chunks honoring min/max constraints
        chunks: list[SemanticChunk] = []
        chunk_start = 0
        for i in range(len(sentences)):
            # Length if we INCLUDE sentence i in current chunk
            tentative = " ".join(sentences[chunk_start : i + 1])
            tentative_len = len(tentative)
            # Length if we keep current chunk closed before sentence i
            current = " ".join(sentences[chunk_start : i])
            current_len = len(current)

            # Break before sentence i if a semantic breakpoint sits
            # exactly here AND we already have enough content
            semantic_break_here = (
                i in breakpoints
                and current_len >= self.min_chunk_chars
                and i > chunk_start
            )

            # Forced break: adding this sentence would blow max
            forced_break = (
                tentative_len > self.max_chunk_chars
                and current_len > 0
            )

            if semantic_break_here or forced_break:
                chunks.append(SemanticChunk(
                    content=current,
                    sentence_indices=(chunk_start, i),
                    metadata={**(metadata or {})},
                ))
                chunk_start = i

        # Tail chunk (whatever remains)
        if chunk_start < len(sentences):
            chunks.append(SemanticChunk(
                content=" ".join(sentences[chunk_start:]),
                sentence_indices=(chunk_start, len(sentences)),
                metadata={**(metadata or {})},
            ))

        # If we emitted no chunks (text below min_chunk_chars total),
        # produce a single tail chunk anyway
        if not chunks:
            chunks.append(SemanticChunk(
                content=" ".join(sentences),
                sentence_indices=(0, len(sentences)),
                metadata=metadata or {},
            ))

        return chunks

    async def chunk_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Chunk a list of LARGESTACK-format documents.

        Each input doc has ``content`` + ``metadata``. Output: one
        document per chunk, with ``metadata.chunk_index`` added.
        """
        out: list[dict[str, Any]] = []
        for doc in documents:
            content = doc.get("content", "")
            base_meta = dict(doc.get("metadata") or {})
            chunks = await self.chunk(content, metadata=base_meta)
            for idx, ch in enumerate(chunks):
                meta = {
                    **base_meta,
                    **ch.metadata,
                    "chunk_index": idx,
                    "chunk_count": len(chunks),
                    "sentence_start": ch.sentence_indices[0],
                    "sentence_end": ch.sentence_indices[1],
                }
                out.append({"content": ch.content, "metadata": meta})
        return out

    @staticmethod
    def _average_windows(
        embeddings: list[list[float]], window: int,
    ) -> list[list[float]]:
        """Smooth embeddings by averaging within a sliding window."""
        if window <= 1 or len(embeddings) <= 1:
            return embeddings
        result: list[list[float]] = []
        for i in range(len(embeddings)):
            start = max(0, i - window // 2)
            end = min(len(embeddings), i + window // 2 + 1)
            chunk = embeddings[start:end]
            dim = len(chunk[0])
            avg = [
                sum(v[d] for v in chunk) / len(chunk)
                for d in range(dim)
            ]
            result.append(avg)
        return result


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "split_sentences",
    "SemanticChunk",
    "SemanticChunker",
]
