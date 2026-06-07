"""Tests for enhanced Embedder with multiple backends."""

import asyncio, sys, os

sys.path.insert(0, ".")


def test_mock_backend_deterministic():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock")
    v1 = asyncio.run(e.embed("hello world"))
    v2 = asyncio.run(e.embed("hello world"))
    assert v1 == v2


def test_mock_similarity_for_related_text():
    from largestack._rag.embedder import Embedder
    from largestack._memory.semantic import cosine_similarity

    e = Embedder(backend="mock")
    # Related texts should have higher similarity than unrelated
    v_cat1 = asyncio.run(e.embed("the cat sat"))
    v_cat2 = asyncio.run(e.embed("a cat playing"))
    v_unrelated = asyncio.run(e.embed("nuclear physics equation"))
    sim_cats = cosine_similarity(v_cat1, v_cat2)
    sim_cross = cosine_similarity(v_cat1, v_unrelated)
    assert sim_cats > sim_cross


def test_empty_text_handled():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock")
    v = asyncio.run(e.embed(""))
    assert len(v) > 0
    assert all(x == 0.0 for x in v)


def test_batch_embedding():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock")
    vecs = asyncio.run(e.embed_batch(["text 1", "text 2", "text 3"]))
    assert len(vecs) == 3
    # Each should be same dim
    assert all(len(v) == len(vecs[0]) for v in vecs)


def test_caching():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock", cache=True)
    v1 = asyncio.run(e.embed("cached text"))
    # Verify cached
    assert e._cache is not None
    assert len(e._cache) == 1
    v2 = asyncio.run(e.embed("cached text"))
    assert v1 == v2
    assert len(e._cache) == 1  # Still 1, served from cache


def test_cache_key_includes_model():
    from largestack._rag.embedder import Embedder

    e1 = Embedder(backend="mock", model="a")
    e2 = Embedder(backend="mock", model="b")
    k1 = e1._cache_key("test")
    k2 = e2._cache_key("test")
    assert k1 != k2


def test_dim_truncation():
    from largestack._rag.embedder import Embedder
    import math

    e = Embedder(backend="mock", dim=32)
    v = asyncio.run(e.embed("some text"))
    assert len(v) == 32
    # Should still be normalized
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 0.01


def test_backend_resolution_without_keys(monkeypatch):
    from largestack._rag.embedder import Embedder

    # Clear any API keys
    for k in (
        "LARGESTACK_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "LARGESTACK_VOYAGE_API_KEY",
        "VOYAGE_API_KEY",
        "LARGESTACK_COHERE_API_KEY",
        "COHERE_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    # B-03 (v0.3.4): mock embeddings now require explicit opt-in
    monkeypatch.setenv("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "1")
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    e = Embedder(backend="auto")
    backend = e._resolve_backend()
    # Should fall back to local (if sentence-transformers installed) or mock (with opt-in)
    assert backend in ("local", "mock")


def test_embedder_fails_loud_without_keys_or_optin(monkeypatch):
    """B-03 (v0.3.4): without API keys, sentence-transformers, or opt-in flag, must raise."""
    from largestack._rag.embedder import Embedder

    for k in (
        "LARGESTACK_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "LARGESTACK_VOYAGE_API_KEY",
        "VOYAGE_API_KEY",
        "LARGESTACK_COHERE_API_KEY",
        "COHERE_API_KEY",
        "LARGESTACK_ALLOW_MOCK_EMBEDDINGS",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    # Patch sentence_transformers import to fail
    import sys, builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kw):
        if name == "sentence_transformers":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    e = Embedder(backend="auto")
    try:
        e._resolve_backend()
        assert False, "should have raised ImportError"
    except ImportError as exc:
        assert "sentence-transformers" in str(exc) or "LARGESTACK_ALLOW_MOCK_EMBEDDINGS" in str(exc)


def test_embedder_fails_loud_in_production(monkeypatch):
    """B-03 (v0.3.4): production env always rejects mock, even with opt-in flag."""
    from largestack._rag.embedder import Embedder

    for k in (
        "LARGESTACK_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "LARGESTACK_VOYAGE_API_KEY",
        "VOYAGE_API_KEY",
        "LARGESTACK_COHERE_API_KEY",
        "COHERE_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.setenv("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "1")  # should be ignored in prod
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kw):
        if name == "sentence_transformers":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    e = Embedder(backend="auto")
    try:
        e._resolve_backend()
        assert False, "production should reject mock embeddings"
    except ImportError as exc:
        assert "production" in str(exc).lower()


def test_model_dims_known():
    from largestack._rag.embedder import Embedder

    assert Embedder.MODEL_DIMS["text-embedding-3-small"] == 1536
    assert Embedder.MODEL_DIMS["voyage-3-large"] == 1024
    assert Embedder.MODEL_DIMS["all-MiniLM-L6-v2"] == 384


def test_batch_uses_cache():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock", cache=True)
    # Pre-warm cache
    asyncio.run(e.embed("one"))
    # Batch that includes cached
    vecs = asyncio.run(e.embed_batch(["one", "two", "three"]))
    assert len(vecs) == 3


def test_batch_empty():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock")
    vecs = asyncio.run(e.embed_batch([]))
    assert vecs == []


def test_cache_lru_eviction():
    from largestack._rag.embedder import Embedder

    e = Embedder(backend="mock", cache=True, cache_size=10)
    # Fill beyond limit
    for i in range(20):
        asyncio.run(e.embed(f"unique text {i}"))
    # Should have evicted some
    assert len(e._cache) <= 10
