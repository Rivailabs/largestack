"""v0.8.0: Tests for 6 new retrieval techniques."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# -------------------- sentence_window_expand --------------------

def test_sentence_window_expand_adds_context():
    from largestack._retrievers import sentence_window_expand

    full_doc = "A" * 200 + "MIDDLE_CHUNK" + "B" * 200
    results = [
        {
            "id": "1",
            "content": "MIDDLE_CHUNK",
            "score": 0.9,
            "metadata": {"full_document": full_doc},
        }
    ]
    out = sentence_window_expand(results, window_chars=50)
    assert "windowed_content" in out[0]
    expanded = out[0]["windowed_content"]
    assert "MIDDLE_CHUNK" in expanded
    assert len(expanded) > len("MIDDLE_CHUNK")  # has context


def test_sentence_window_handles_missing_full_doc():
    from largestack._retrievers import sentence_window_expand
    results = [{"id": "1", "content": "chunk", "metadata": {}}]
    out = sentence_window_expand(results, window_chars=50)
    assert out[0]["windowed_content"] == "chunk"


def test_sentence_window_validates_window():
    from largestack._retrievers import sentence_window_expand
    with pytest.raises(ValueError):
        sentence_window_expand([], window_chars=-1)


# -------------------- parent_document_retrieve --------------------

@pytest.mark.asyncio
async def test_parent_document_dedup_and_returns_full():
    """Multiple chunks from same parent → one parent doc."""
    from largestack._retrievers import parent_document_retrieve

    chunks = [
        {"id": "c1", "score": 0.95, "metadata": {"parent_id": "P1"}},
        {"id": "c2", "score": 0.90, "metadata": {"parent_id": "P1"}},
        {"id": "c3", "score": 0.85, "metadata": {"parent_id": "P2"}},
    ]
    parent_data = {
        "P1": {"id": "P1", "content": "Parent 1 full text"},
        "P2": {"id": "P2", "content": "Parent 2 full text"},
    }

    async def chunk_retriever(q, k):
        return chunks
    async def parent_lookup(pid):
        return parent_data.get(pid)

    out = await parent_document_retrieve(
        "q", chunk_retriever=chunk_retriever, parent_lookup=parent_lookup, k=5,
    )
    # 2 unique parents, in retrieval order
    assert len(out) == 2
    assert out[0]["id"] == "P1"
    assert out[1]["id"] == "P2"


@pytest.mark.asyncio
async def test_parent_document_caps_at_k():
    from largestack._retrievers import parent_document_retrieve
    chunks = [
        {"id": f"c{i}", "score": 1.0 - i*0.1, "metadata": {"parent_id": f"P{i}"}}
        for i in range(10)
    ]
    async def cr(q, k): return chunks
    async def pl(pid): return {"id": pid, "content": pid}
    out = await parent_document_retrieve("q", chunk_retriever=cr, parent_lookup=pl, k=3)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_parent_document_handles_lookup_failure():
    from largestack._retrievers import parent_document_retrieve
    chunks = [{"id": "c1", "score": 0.9, "metadata": {"parent_id": "X"}}]
    async def cr(q, k): return chunks
    async def pl(pid): raise RuntimeError("DB down")
    out = await parent_document_retrieve("q", chunk_retriever=cr, parent_lookup=pl, k=5)
    assert out == []


# -------------------- auto_merging_retrieve --------------------

@pytest.mark.asyncio
async def test_auto_merging_merges_when_threshold_met():
    """If 3 of 4 leaves of a parent are retrieved, return parent doc."""
    from largestack._retrievers import auto_merging_retrieve

    leaves = [
        {"id": "L1", "score": 0.9, "metadata": {"parent_id": "P1", "parent_total_leaves": 4}},
        {"id": "L2", "score": 0.85, "metadata": {"parent_id": "P1", "parent_total_leaves": 4}},
        {"id": "L3", "score": 0.80, "metadata": {"parent_id": "P1", "parent_total_leaves": 4}},
        {"id": "L99", "score": 0.7, "metadata": {"parent_id": "P9", "parent_total_leaves": 5}},
    ]
    async def lr(q, k): return leaves
    async def pl(pid): return {"id": pid, "content": f"parent {pid}"}

    out = await auto_merging_retrieve(
        "q", leaf_retriever=lr, parent_lookup=pl, k=10, merge_threshold=0.5,
    )
    # P1 should be merged (3/4 = 0.75 >= 0.5); L99 stays as leaf
    ids = [d["id"] for d in out]
    assert "P1" in ids
    assert "L99" in ids
    assert "L1" not in ids  # consumed into P1
    p1 = next(d for d in out if d["id"] == "P1")
    assert p1["metadata"].get("merged_from_n_leaves") == 3


@pytest.mark.asyncio
async def test_auto_merging_does_not_merge_below_threshold():
    from largestack._retrievers import auto_merging_retrieve
    leaves = [
        {"id": "L1", "score": 0.9, "metadata": {"parent_id": "P1", "parent_total_leaves": 10}},
    ]
    async def lr(q, k): return leaves
    async def pl(pid): return {"id": pid, "content": "p"}
    out = await auto_merging_retrieve(
        "q", leaf_retriever=lr, parent_lookup=pl, merge_threshold=0.5,
    )
    # 1/10 = 0.1 < 0.5 → no merge
    assert out[0]["id"] == "L1"


@pytest.mark.asyncio
async def test_auto_merging_validates():
    from largestack._retrievers import auto_merging_retrieve
    async def lr(q, k): return []
    async def pl(pid): return {}
    with pytest.raises(ValueError):
        await auto_merging_retrieve("q", leaf_retriever=lr, parent_lookup=pl, merge_threshold=1.5)
    with pytest.raises(ValueError):
        await auto_merging_retrieve("q", leaf_retriever=lr, parent_lookup=pl, k=0)


# -------------------- recursive_retrieve --------------------

@pytest.mark.asyncio
async def test_recursive_retrieve_follows_references():
    """First retrieval finds doc1, which references doc2 — both returned."""
    from largestack._retrievers import recursive_retrieve

    async def initial(q, k):
        return [{"id": "doc1", "score": 0.9,
                 "metadata": {"references": ["doc2"]}}]
    async def follow(ref_id):
        if ref_id == "doc2":
            return {"id": "doc2", "score": 0.7, "metadata": {}}
        return None

    out = await recursive_retrieve(
        "q", initial_retriever=initial, follow_lookup=follow, k=5, depth=2,
    )
    ids = [d["id"] for d in out]
    assert "doc1" in ids
    assert "doc2" in ids


@pytest.mark.asyncio
async def test_recursive_dedups_already_seen():
    """If a referenced doc was already retrieved, don't add it again."""
    from largestack._retrievers import recursive_retrieve

    async def initial(q, k):
        return [
            {"id": "A", "score": 0.9, "metadata": {"references": ["B"]}},
            {"id": "B", "score": 0.8, "metadata": {"references": ["A"]}},
        ]
    async def follow(ref_id):
        return {"id": ref_id, "score": 0.0}
    out = await recursive_retrieve(
        "q", initial_retriever=initial, follow_lookup=follow, k=5, depth=3,
    )
    ids = [d["id"] for d in out]
    assert ids.count("A") == 1
    assert ids.count("B") == 1


@pytest.mark.asyncio
async def test_recursive_respects_depth_1():
    """depth=1 means no recursion."""
    from largestack._retrievers import recursive_retrieve
    follow_calls = [0]

    async def initial(q, k):
        return [{"id": "A", "metadata": {"references": ["B", "C"]}}]
    async def follow(ref_id):
        follow_calls[0] += 1
        return {"id": ref_id}

    out = await recursive_retrieve(
        "q", initial_retriever=initial, follow_lookup=follow, k=5, depth=1,
    )
    assert follow_calls[0] == 0
    assert [d["id"] for d in out] == ["A"]


# -------------------- time_weighted_rerank --------------------

def test_time_weighted_rerank_boosts_recent():
    from largestack._retrievers import time_weighted_rerank
    now = 1_000_000.0
    results = [
        {"id": "old", "score": 0.9,
         "metadata": {"timestamp": now - 365 * 24 * 3600}},  # 1 year old
        {"id": "new", "score": 0.7,
         "metadata": {"timestamp": now - 60}},  # 1 minute old
    ]
    out = time_weighted_rerank(results, decay_rate=0.001, now=now)
    # The recent doc should now rank higher
    assert out[0]["id"] == "new"


def test_time_weighted_handles_missing_timestamp():
    from largestack._retrievers import time_weighted_rerank
    results = [{"id": "x", "score": 0.5, "metadata": {}}]
    out = time_weighted_rerank(results)
    assert out[0]["time_weighted_score"] == 0.5


def test_time_weighted_validates_decay():
    from largestack._retrievers import time_weighted_rerank
    with pytest.raises(ValueError):
        time_weighted_rerank([], decay_rate=1.0)
    with pytest.raises(ValueError):
        time_weighted_rerank([], decay_rate=-0.1)


# -------------------- document_summary_retrieve --------------------

@pytest.mark.asyncio
async def test_document_summary_retrieve():
    from largestack._retrievers import document_summary_retrieve
    summaries = [
        {"id": "s1", "score": 0.95, "metadata": {"doc_id": "D1"}},
        {"id": "s2", "score": 0.80, "metadata": {"doc_id": "D2"}},
    ]
    full_docs = {
        "D1": {"id": "D1", "content": "FULL doc 1", "metadata": {}},
        "D2": {"id": "D2", "content": "FULL doc 2", "metadata": {}},
    }
    async def summary_ret(q, k): return summaries
    async def full_lookup(did): return full_docs.get(did)

    out = await document_summary_retrieve(
        "q", summary_retriever=summary_ret, full_doc_lookup=full_lookup, k=5,
    )
    assert len(out) == 2
    assert "FULL doc 1" in out[0]["content"]
    assert out[0]["score"] == 0.95


@pytest.mark.asyncio
async def test_document_summary_handles_missing_doc():
    from largestack._retrievers import document_summary_retrieve
    summaries = [{"id": "s", "score": 0.9, "metadata": {"doc_id": "missing"}}]
    async def summary_ret(q, k): return summaries
    async def full_lookup(did): return None  # not found
    out = await document_summary_retrieve(
        "q", summary_retriever=summary_ret, full_doc_lookup=full_lookup, k=5,
    )
    assert out == []
