"""v0.14.0: Tests for semantic chunking."""
from __future__ import annotations

import pytest


# -------------------- split_sentences --------------------

def test_split_sentences_basic():
    from largestack._loaders.semantic_chunking import split_sentences
    text = "Hello world. This is sentence two. And three!"
    s = split_sentences(text)
    assert len(s) == 3
    assert s[0] == "Hello world."


def test_split_sentences_empty_input():
    from largestack._loaders.semantic_chunking import split_sentences
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_split_sentences_indic_danda():
    from largestack._loaders.semantic_chunking import split_sentences
    # Hindi text with Danda
    text = "नमस्ते। यह हिंदी है। तीसरा वाक्य।"
    s = split_sentences(text)
    assert len(s) >= 2  # at least split on Danda


def test_split_sentences_handles_question_marks():
    from largestack._loaders.semantic_chunking import split_sentences
    text = "What is this? It is a test. Really!"
    s = split_sentences(text)
    assert len(s) == 3


# -------------------- SemanticChunker validation --------------------

def test_chunker_validates_breakpoint_distance():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    with pytest.raises(ValueError, match="breakpoint_distance"):
        SemanticChunker(embedder=HashingEmbedder(), breakpoint_distance=3.0)


def test_chunker_validates_min_chunk_chars():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    with pytest.raises(ValueError, match="min_chunk_chars"):
        SemanticChunker(embedder=HashingEmbedder(), min_chunk_chars=0)


def test_chunker_validates_max_vs_min():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    with pytest.raises(ValueError, match="max_chunk_chars"):
        SemanticChunker(
            embedder=HashingEmbedder(),
            min_chunk_chars=500, max_chunk_chars=100,
        )


# -------------------- chunk() core behavior --------------------

@pytest.mark.asyncio
async def test_chunk_empty_text():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(embedder=HashingEmbedder())
    assert await chunker.chunk("") == []


@pytest.mark.asyncio
async def test_chunk_single_sentence():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(embedder=HashingEmbedder())
    chunks = await chunker.chunk("Just one sentence.")
    assert len(chunks) == 1
    assert chunks[0].content == "Just one sentence."


@pytest.mark.asyncio
async def test_chunk_preserves_sentence_boundaries():
    """Chunks should not split mid-sentence."""
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(
        embedder=HashingEmbedder(),
        min_chunk_chars=10, max_chunk_chars=200,
        breakpoint_distance=0.1,  # break aggressively
    )
    text = "First sentence here. Second sentence. Third one. Fourth."
    chunks = await chunker.chunk(text)
    # Each chunk's content must end with sentence-terminator
    for c in chunks:
        last = c.content.rstrip()[-1] if c.content.rstrip() else ""
        assert last in ".!?।…"


@pytest.mark.asyncio
async def test_chunk_respects_max_chars():
    """Forces a break when exceeding max_chunk_chars."""
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(
        embedder=HashingEmbedder(),
        breakpoint_distance=1.99,  # max — effectively disables semantic break
        min_chunk_chars=10,
        max_chunk_chars=80,
    )
    # Each sentence is ~30 chars; total ~150 chars
    text = (
        "Sentence one is here now. Sentence two is now here. "
        "Sentence three follows. Sentence four ends it."
    )
    chunks = await chunker.chunk(text)
    # Should produce > 1 chunk due to max_chunk_chars
    assert len(chunks) > 1
    for c in chunks[:-1]:
        # Non-terminal chunks should be near max_chunk_chars
        assert len(c.content) >= 10


@pytest.mark.asyncio
async def test_chunk_preserves_metadata():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(embedder=HashingEmbedder())
    chunks = await chunker.chunk(
        "First sentence. Second sentence.",
        metadata={"source": "test.txt", "loader": "txt"},
    )
    for c in chunks:
        assert c.metadata.get("source") == "test.txt"


@pytest.mark.asyncio
async def test_chunk_documents_adds_chunk_index():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(
        embedder=HashingEmbedder(),
        breakpoint_distance=0.0001,  # break almost everywhere
        min_chunk_chars=1,
        max_chunk_chars=200,
    )
    docs = [{
        "content": "One. Two. Three. Four.",
        "metadata": {"source": "x.txt"},
    }]
    out = await chunker.chunk_documents(docs)
    assert len(out) > 1
    indices = [d["metadata"]["chunk_index"] for d in out]
    assert indices == list(range(len(out)))
    for d in out:
        assert d["metadata"]["chunk_count"] == len(out)
        assert d["metadata"]["source"] == "x.txt"


@pytest.mark.asyncio
async def test_chunk_documents_with_multiple_inputs():
    from largestack._loaders.semantic_chunking import SemanticChunker
    from largestack._memory.vector_store import HashingEmbedder
    chunker = SemanticChunker(embedder=HashingEmbedder())
    docs = [
        {"content": "Doc one content.", "metadata": {"id": "a"}},
        {"content": "Doc two content.", "metadata": {"id": "b"}},
    ]
    out = await chunker.chunk_documents(docs)
    sources = {d["metadata"]["id"] for d in out}
    assert sources == {"a", "b"}
