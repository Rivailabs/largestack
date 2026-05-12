"""v0.12.0: Tests for long-term hierarchical memory module.

Closes the Letta / Mem0 / Zep gap. Tests cover:
- Entry lifecycle (add/get/update/delete)
- Multi-tenancy isolation
- Hierarchical tiers (core / recall / archival)
- Memory scopes (episodic / semantic / procedural)
- DPDP TTL + purpose + lawful_basis
- Context-window assembly
- Fact extraction
- Both InMemoryStore and SQLiteStore
- Right-to-erasure (forget + forget_user)
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Entry lifecycle --------------------

@pytest.mark.asyncio
async def test_in_memory_store_add_and_get():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="Hello",
    )
    await store.add(e)
    got = await store.get("e1")
    assert got is not None
    assert got.content == "Hello"


@pytest.mark.asyncio
async def test_in_memory_store_get_missing():
    from largestack._memory.long_term import InMemoryLongTermStore
    store = InMemoryLongTermStore()
    assert await store.get("nope") is None


@pytest.mark.asyncio
async def test_in_memory_store_delete():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="x",
    )
    await store.add(e)
    assert await store.delete("e1") is True
    assert await store.delete("e1") is False
    assert await store.get("e1") is None


@pytest.mark.asyncio
async def test_in_memory_store_update():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="core", scope="semantic", content="original",
    )
    await store.add(e)
    e.content = "updated"
    await store.update(e)
    got = await store.get("e1")
    assert got.content == "updated"


# -------------------- Multi-tenancy isolation --------------------

@pytest.mark.asyncio
async def test_tenant_isolation_in_list():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    await store.add(LongTermMemoryEntry(
        id="a", tenant_id="t1", user_id="u1",
        tier="core", scope="semantic", content="t1 secret",
    ))
    await store.add(LongTermMemoryEntry(
        id="b", tenant_id="t2", user_id="u1",
        tier="core", scope="semantic", content="t2 secret",
    ))
    t1 = await store.list(tenant_id="t1")
    t2 = await store.list(tenant_id="t2")
    assert len(t1) == 1
    assert len(t2) == 1
    assert t1[0].content == "t1 secret"
    assert t2[0].content == "t2 secret"


@pytest.mark.asyncio
async def test_tenant_isolation_in_search():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    await store.add(LongTermMemoryEntry(
        id="a", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic",
        content="confidential AAACR1234C details",
    ))
    await store.add(LongTermMemoryEntry(
        id="b", tenant_id="t2", user_id="u1",
        tier="recall", scope="episodic",
        content="other tenant AAACR1234C info",
    ))
    # t1 search must NOT see t2's entry
    results = await store.search(
        tenant_id="t1", user_id="u1", query="AAACR1234C",
    )
    assert len(results) == 1
    assert results[0].tenant_id == "t1"


@pytest.mark.asyncio
async def test_user_isolation_within_tenant():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    await store.add(LongTermMemoryEntry(
        id="a", tenant_id="t1", user_id="alice",
        tier="core", scope="semantic", content="alice data",
    ))
    await store.add(LongTermMemoryEntry(
        id="b", tenant_id="t1", user_id="bob",
        tier="core", scope="semantic", content="bob data",
    ))
    alice_data = await store.list(tenant_id="t1", user_id="alice")
    assert len(alice_data) == 1
    assert alice_data[0].content == "alice data"


# -------------------- Tier filtering --------------------

@pytest.mark.asyncio
async def test_filter_by_tier():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    for tier in ("core", "recall", "archival"):
        await store.add(LongTermMemoryEntry(
            id=f"e_{tier}", tenant_id="t1", user_id="u1",
            tier=tier, scope="semantic", content=f"{tier} data",
        ))
    core = await store.list(tenant_id="t1", tier="core")
    archival = await store.list(tenant_id="t1", tier="archival")
    assert len(core) == 1
    assert core[0].tier == "core"
    assert len(archival) == 1
    assert archival[0].tier == "archival"


@pytest.mark.asyncio
async def test_filter_by_scope():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    for scope in ("episodic", "semantic", "procedural"):
        await store.add(LongTermMemoryEntry(
            id=f"e_{scope}", tenant_id="t1", user_id="u1",
            tier="archival", scope=scope, content=f"{scope}",
        ))
    semantic = await store.list(tenant_id="t1", scope="semantic")
    assert len(semantic) == 1
    assert semantic[0].scope == "semantic"


# -------------------- Search ranking --------------------

@pytest.mark.asyncio
async def test_search_substring_match_ranks_higher():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    await store.add(LongTermMemoryEntry(
        id="exact", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="exact phrase here please",
    ))
    await store.add(LongTermMemoryEntry(
        id="partial", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="phrase exact something different",
    ))
    results = await store.search(
        tenant_id="t1", user_id="u1", query="exact phrase",
    )
    assert results[0].id == "exact"


@pytest.mark.asyncio
async def test_search_excludes_expired():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    fresh = LongTermMemoryEntry(
        id="fresh", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="findme",
    )
    expired = LongTermMemoryEntry(
        id="exp", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="findme",
        created_at=time.time() - 100, ttl_seconds=10,
    )
    await store.add(fresh)
    await store.add(expired)
    results = await store.search(
        tenant_id="t1", user_id="u1", query="findme",
    )
    assert len(results) == 1
    assert results[0].id == "fresh"


# -------------------- DPDP fields --------------------

def test_entry_default_dpdp_fields():
    from largestack._memory.long_term import LongTermMemoryEntry
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="core", scope="semantic", content="x",
    )
    # Defaults — empty strings (audit risk if used in production)
    assert e.purpose == ""
    assert e.lawful_basis == ""
    assert e.ttl_seconds is None


def test_entry_is_expired():
    from largestack._memory.long_term import LongTermMemoryEntry
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic", content="x",
        created_at=time.time() - 100, ttl_seconds=10,
    )
    assert e.is_expired() is True


def test_entry_no_ttl_never_expires():
    from largestack._memory.long_term import LongTermMemoryEntry
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="x",
        created_at=0,  # 1970
    )
    assert e.is_expired() is False


@pytest.mark.asyncio
async def test_purge_expired_only_removes_expired():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry,
    )
    store = InMemoryLongTermStore()
    await store.add(LongTermMemoryEntry(
        id="fresh", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic", content="fresh",
    ))
    await store.add(LongTermMemoryEntry(
        id="expired", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic", content="old",
        created_at=time.time() - 10000, ttl_seconds=100,
    ))
    purged = await store.purge_expired(tenant_id="t1")
    assert purged == 1
    remaining = await store.list(tenant_id="t1")
    assert len(remaining) == 1
    assert remaining[0].id == "fresh"


# -------------------- Manager - constructor --------------------

def test_manager_requires_tenant_id():
    from largestack._memory.long_term import LongTermMemoryManager
    with pytest.raises(ValueError, match="tenant_id"):
        LongTermMemoryManager(tenant_id="", user_id="u1")


def test_manager_requires_user_id():
    from largestack._memory.long_term import LongTermMemoryManager
    with pytest.raises(ValueError, match="user_id"):
        LongTermMemoryManager(tenant_id="t1", user_id="")


# -------------------- Manager - tier-aware add --------------------

@pytest.mark.asyncio
async def test_manager_add_core_with_dpdp_fields():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    e = await mgr.add_core(
        "User prefers Hindi",
        tag="preferences",
        purpose="personalization",
        lawful_basis="consent",
    )
    assert e.tier == "core"
    assert e.tenant_id == "t1"
    assert e.user_id == "u1"
    assert e.tag == "preferences"
    assert e.purpose == "personalization"
    assert e.lawful_basis == "consent"


@pytest.mark.asyncio
async def test_manager_add_recall_default_ttl():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    e = await mgr.add_recall("User asked about loan rates")
    # Default TTL = 30 days
    assert e.ttl_seconds == 30 * 24 * 3600


@pytest.mark.asyncio
async def test_manager_add_archival_no_default_ttl():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    e = await mgr.add_archival("User's company is RivaiLabs")
    assert e.ttl_seconds is None  # archival = retain indefinitely


# -------------------- Manager - context block --------------------

@pytest.mark.asyncio
async def test_get_core_block_truncates_at_limit():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(
        tenant_id="t1", user_id="u1", core_block_chars=80,
    )
    await mgr.add_core("a" * 50, tag="t1")
    await mgr.add_core("b" * 50, tag="t2")
    block = await mgr.get_core_block()
    # Should fit at most one entry given the budget
    a_count = block.count("a")
    b_count = block.count("b")
    # Whichever was kept, the other should be truncated out
    assert (a_count >= 50) ^ (b_count >= 50), (
        f"expected exactly one entry, got a={a_count} b={b_count}"
    )
    assert len(block) <= 80 + 1


@pytest.mark.asyncio
async def test_get_core_block_empty_when_no_entries():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    block = await mgr.get_core_block()
    assert block == ""


@pytest.mark.asyncio
async def test_get_core_block_skips_expired():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryEntry, LongTermMemoryManager,
    )
    store = InMemoryLongTermStore()
    # Manually add an expired core entry
    await store.add(LongTermMemoryEntry(
        id="exp", tenant_id="t1", user_id="u1",
        tier="core", scope="semantic", content="EXPIRED",
        created_at=time.time() - 10000, ttl_seconds=100,
    ))
    mgr = LongTermMemoryManager(
        store=store, tenant_id="t1", user_id="u1",
    )
    block = await mgr.get_core_block()
    assert "EXPIRED" not in block


# -------------------- Manager - search by tier --------------------

@pytest.mark.asyncio
async def test_search_recall_only_returns_recall_tier():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_archival("findme in archival")
    await mgr.add_recall("findme in recall")
    await mgr.add_core("findme in core")
    results = await mgr.search_recall("findme")
    assert len(results) == 1
    assert results[0].tier == "recall"


@pytest.mark.asyncio
async def test_search_archival_only_returns_archival():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_archival("user is from Bengaluru")
    await mgr.add_recall("user mentioned Bengaluru today")
    results = await mgr.search_archival("Bengaluru")
    assert len(results) == 1
    assert results[0].tier == "archival"


# -------------------- Manager - context assembly --------------------

@pytest.mark.asyncio
async def test_build_context_assembles_all_sections():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_core("Persona: helpful India fintech assistant",
                       tag="persona")
    await mgr.add_recall("User asked about Aadhaar OKYC last week")
    # Make archival entry match the query
    await mgr.add_archival("User's company uses Aadhaar OKYC for KYC")
    ctx = await mgr.build_context("Aadhaar")
    assert "Core Memory" in ctx
    assert "persona" in ctx.lower()
    assert "Recent Relevant Memories" in ctx
    assert "Long-term Facts" in ctx


@pytest.mark.asyncio
async def test_build_context_skips_empty_sections():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    # Only core, no recall or archival
    await mgr.add_core("only core data", tag="x")
    ctx = await mgr.build_context("anything")
    assert "Core Memory" in ctx
    assert "Recent Relevant" not in ctx
    assert "Long-term Facts" not in ctx


# -------------------- Manager - stats --------------------

@pytest.mark.asyncio
async def test_stats_counts_by_tier_and_scope():
    from largestack._memory.long_term import LongTermMemoryManager
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_core("a", scope="semantic")
    await mgr.add_recall("b", scope="episodic")
    await mgr.add_recall("c", scope="episodic")
    await mgr.add_archival("d", scope="procedural")
    s = await mgr.stats()
    assert s.total == 4
    assert s.by_tier["core"] == 1
    assert s.by_tier["recall"] == 2
    assert s.by_tier["archival"] == 1
    assert s.by_scope["semantic"] == 1
    assert s.by_scope["episodic"] == 2
    assert s.by_scope["procedural"] == 1


# -------------------- Manager - DPDP right-to-erasure --------------------

@pytest.mark.asyncio
async def test_forget_deletes_only_own_user_entry():
    """forget() must enforce tenant + user scoping."""
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryManager,
    )
    store = InMemoryLongTermStore()
    alice = LongTermMemoryManager(
        store=store, tenant_id="t1", user_id="alice",
    )
    bob = LongTermMemoryManager(
        store=store, tenant_id="t1", user_id="bob",
    )
    bob_entry = await bob.add_archival("bob's secret")
    # Alice trying to forget Bob's entry must fail
    deleted = await alice.forget(bob_entry.id)
    assert deleted is False
    # Bob's entry still in the store
    still_there = await store.get(bob_entry.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_forget_user_deletes_all_user_entries():
    from largestack._memory.long_term import (
        InMemoryLongTermStore, LongTermMemoryManager,
    )
    store = InMemoryLongTermStore()
    alice = LongTermMemoryManager(
        store=store, tenant_id="t1", user_id="alice",
    )
    bob = LongTermMemoryManager(
        store=store, tenant_id="t1", user_id="bob",
    )
    await alice.add_core("alice 1")
    await alice.add_recall("alice 2")
    await alice.add_archival("alice 3")
    await bob.add_core("bob 1")

    count = await alice.forget_user()
    assert count == 3

    # Bob's data unaffected
    bob_data = await bob.list_all()
    assert len(bob_data) == 1


# -------------------- SQLite backend --------------------

@pytest.mark.asyncio
async def test_sqlite_store_basic_ops():
    from largestack._memory.long_term import (
        SQLiteLongTermStore, LongTermMemoryEntry,
    )
    store = SQLiteLongTermStore(":memory:")
    e = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="sqlite test",
        purpose="personalization", lawful_basis="consent",
    )
    await store.add(e)
    got = await store.get("e1")
    assert got is not None
    assert got.content == "sqlite test"
    assert got.purpose == "personalization"
    assert got.lawful_basis == "consent"


@pytest.mark.asyncio
async def test_sqlite_store_search():
    from largestack._memory.long_term import (
        SQLiteLongTermStore, LongTermMemoryEntry,
    )
    store = SQLiteLongTermStore(":memory:")
    await store.add(LongTermMemoryEntry(
        id="a", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="The user works at RivaiLabs",
    ))
    await store.add(LongTermMemoryEntry(
        id="b", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="Unrelated content here",
    ))
    results = await store.search(
        tenant_id="t1", user_id="u1", query="RivaiLabs",
    )
    assert len(results) == 1
    assert results[0].id == "a"


@pytest.mark.asyncio
async def test_sqlite_store_tenant_isolation():
    from largestack._memory.long_term import (
        SQLiteLongTermStore, LongTermMemoryEntry,
    )
    store = SQLiteLongTermStore(":memory:")
    await store.add(LongTermMemoryEntry(
        id="a", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic", content="t1 data",
    ))
    await store.add(LongTermMemoryEntry(
        id="b", tenant_id="t2", user_id="u1",
        tier="archival", scope="semantic", content="t2 data",
    ))
    t1 = await store.list(tenant_id="t1")
    assert len(t1) == 1
    assert t1[0].tenant_id == "t1"


@pytest.mark.asyncio
async def test_sqlite_store_purge_expired():
    from largestack._memory.long_term import (
        SQLiteLongTermStore, LongTermMemoryEntry,
    )
    store = SQLiteLongTermStore(":memory:")
    await store.add(LongTermMemoryEntry(
        id="exp", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic", content="old",
        created_at=time.time() - 1000, ttl_seconds=10,
    ))
    await store.add(LongTermMemoryEntry(
        id="fresh", tenant_id="t1", user_id="u1",
        tier="recall", scope="episodic", content="new",
    ))
    purged = await store.purge_expired(tenant_id="t1")
    assert purged == 1


# -------------------- Fact extraction --------------------

@pytest.mark.asyncio
async def test_extract_facts_parses_json_array():
    from largestack._memory.long_term import extract_facts
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content=(
        '[{"content": "User prefers Hindi", "scope": "semantic", '
        '"tag": "preferences"}]'
    )))
    facts = await extract_facts(judge, turn="हिंदी में बोलिए please")
    assert len(facts) == 1
    assert facts[0]["content"] == "User prefers Hindi"
    assert facts[0]["scope"] == "semantic"
    assert facts[0]["tag"] == "preferences"


@pytest.mark.asyncio
async def test_extract_facts_handles_code_fence_wrapper():
    from largestack._memory.long_term import extract_facts
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content=(
        '```json\n[{"content": "x", "scope": "semantic"}]\n```'
    )))
    facts = await extract_facts(judge, turn="anything")
    assert len(facts) == 1


@pytest.mark.asyncio
async def test_extract_facts_handles_invalid_json():
    from largestack._memory.long_term import extract_facts
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content="not json"))
    facts = await extract_facts(judge, turn="x")
    assert facts == []


@pytest.mark.asyncio
async def test_extract_facts_caps_at_max():
    from largestack._memory.long_term import extract_facts
    judge = MagicMock()
    many = [
        {"content": f"fact {i}", "scope": "semantic"} for i in range(20)
    ]
    import json as _j
    judge.run = AsyncMock(return_value=MagicMock(
        content=_j.dumps(many),
    ))
    facts = await extract_facts(judge, turn="x", max_facts=3)
    assert len(facts) == 3


@pytest.mark.asyncio
async def test_extract_facts_normalizes_invalid_scope():
    from largestack._memory.long_term import extract_facts
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content=(
        '[{"content": "x", "scope": "BOGUS_SCOPE"}]'
    )))
    facts = await extract_facts(judge, turn="x")
    assert facts[0]["scope"] == "semantic"  # normalized to default


@pytest.mark.asyncio
async def test_extract_and_store_writes_to_archival_by_default():
    from largestack._memory.long_term import (
        LongTermMemoryManager, extract_and_store,
    )
    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content=(
        '[{"content": "User is in Bengaluru", "scope": "semantic", '
        '"tag": "location"}]'
    )))
    stored = await extract_and_store(
        mgr, judge, turn="I'm based in Bengaluru",
    )
    assert len(stored) == 1
    assert stored[0].tier == "archival"
    assert stored[0].source == "extracted"
    assert stored[0].purpose == "personalization"


# -------------------- Entry serialization --------------------

def test_entry_to_dict_and_back():
    from largestack._memory.long_term import LongTermMemoryEntry
    original = LongTermMemoryEntry(
        id="e1", tenant_id="t1", user_id="u1",
        tier="core", scope="semantic", content="test",
        tag="x", purpose="p", lawful_basis="consent",
        ttl_seconds=100.0,
    )
    d = original.to_dict()
    rebuilt = LongTermMemoryEntry.from_dict(d)
    assert rebuilt.id == original.id
    assert rebuilt.content == original.content
    assert rebuilt.purpose == original.purpose


def test_entry_from_dict_tolerates_extra_keys():
    """Forward compatibility: ignore unknown fields."""
    from largestack._memory.long_term import LongTermMemoryEntry
    d = {
        "id": "e1", "tenant_id": "t1", "user_id": "u1",
        "tier": "core", "scope": "semantic", "content": "x",
        "future_field_we_dont_know_about": "ignored",
    }
    e = LongTermMemoryEntry.from_dict(d)
    assert e.content == "x"


# -------------------- Format helper --------------------

def test_format_ago_minutes():
    from largestack._memory.long_term import _format_ago
    assert _format_ago(30) == "just now"
    assert "min ago" in _format_ago(120)
    assert "hr ago" in _format_ago(7200)
    assert "days ago" in _format_ago(86400 * 3)
    assert "weeks ago" in _format_ago(86400 * 14)
    assert "months ago" in _format_ago(86400 * 60)
