"""Tests for enhanced reranker with multi-backend support."""

import sys

sys.path.insert(0, ".")


def test_keyword_basic():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    docs = [
        {"text": "The cat sat on the mat"},
        {"text": "Dogs are great pets"},
        {"text": "The cat purrs when happy"},
    ]
    results = r.rerank("cat behavior", docs, top_k=2)
    assert len(results) == 2
    # Cat-related should rank higher
    assert "cat" in results[0]["text"].lower()


def test_keyword_ngram_bonus():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    docs = [
        {"text": "machine learning algorithms are complex"},
        {"text": "machine is a noun and learning is a verb"},
    ]
    results = r.rerank("machine learning", docs, top_k=2)
    # First doc has the phrase as bigram → ranks higher
    assert results[0]["text"].startswith("machine learning")


def test_empty_documents():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    assert r.rerank("test", [], top_k=5) == []


def test_empty_query():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    docs = [{"text": "a"}, {"text": "b"}]
    # Empty query → returns first N docs
    results = r.rerank("", docs, top_k=1)
    assert len(results) == 1


def test_top_k_zero():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    docs = [{"text": "a"}]
    assert r.rerank("q", docs, top_k=0) == []


def test_min_score_filtering():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword", min_score=0.5)
    docs = [
        {"text": "completely unrelated content"},
        {"text": "the exact query matches here directly"},
    ]
    results = r.rerank("exact query matches", docs, top_k=5)
    # Only high-scoring docs kept
    for d in results:
        assert d["rerank_score"] >= 0.5


def test_preserves_doc_fields():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    docs = [
        {"text": "hello world", "id": "1", "source": "file1.txt"},
    ]
    results = r.rerank("hello", docs, top_k=1)
    assert results[0]["id"] == "1"
    assert results[0]["source"] == "file1.txt"
    assert "rerank_score" in results[0]


def test_custom_reranker():
    from largestack._rag.reranker import Reranker

    def custom(query, docs):
        # Reverse order as a joke
        return list(reversed(docs))

    r = Reranker(mode="custom", custom_fn=custom)
    docs = [{"text": "A"}, {"text": "B"}, {"text": "C"}]
    results = r.rerank("q", docs, top_k=3)
    assert results[0]["text"] == "C"


def test_bad_mode():
    from largestack._rag.reranker import Reranker

    try:
        Reranker(mode="bogus")
        assert False
    except ValueError:
        pass


def test_mode_resolution():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="cohere")
    # Should set the default Cohere model
    assert "rerank" in r.model


def test_fallback_without_api_key():
    import os
    from largestack._rag.reranker import Reranker

    # Ensure no cohere key
    for k in ("LARGESTACK_COHERE_API_KEY", "COHERE_API_KEY"):
        os.environ.pop(k, None)
    r = Reranker(mode="cohere")
    docs = [{"text": "hello world"}, {"text": "foo bar"}]
    results = r.rerank("hello", docs, top_k=2)
    # Should fallback to keyword and still return results
    assert len(results) > 0


def test_stats():
    from largestack._rag.reranker import Reranker

    r = Reranker(mode="keyword")
    s = r.stats
    assert s["mode"] == "keyword"
    assert "cache_size" in s
