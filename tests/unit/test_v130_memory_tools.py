"""v0.13.0: Tests for self-editing memory tools (Letta pattern)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# -------------------- core_memory_replace --------------------

@pytest.mark.asyncio
async def test_core_memory_replace_creates_when_missing():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_replace

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    result = await core_memory_replace(
        mgr, tag="persona", new_content="helpful India-fintech assistant",
    )
    assert "Created" in result or "Replaced" in result

    block = await mgr.get_core_block()
    assert "helpful India-fintech assistant" in block


@pytest.mark.asyncio
async def test_core_memory_replace_overwrites_existing():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_replace

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_core("original content", tag="persona")

    await core_memory_replace(
        mgr, tag="persona", new_content="updated content",
    )

    block = await mgr.get_core_block()
    assert "updated content" in block
    assert "original content" not in block


@pytest.mark.asyncio
async def test_core_memory_replace_requires_tag():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_replace

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    with pytest.raises(ValueError, match="tag"):
        await core_memory_replace(mgr, tag="", new_content="x")


@pytest.mark.asyncio
async def test_core_memory_replace_requires_content():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_replace

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    with pytest.raises(ValueError, match="content"):
        await core_memory_replace(mgr, tag="x", new_content="")


# -------------------- core_memory_append --------------------

@pytest.mark.asyncio
async def test_core_memory_append_concatenates():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_append

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_core("first preference", tag="prefs")

    await core_memory_append(
        mgr, tag="prefs", content_to_append="second preference",
    )

    block = await mgr.get_core_block()
    assert "first preference" in block
    assert "second preference" in block


@pytest.mark.asyncio
async def test_core_memory_append_creates_when_missing():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import core_memory_append

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await core_memory_append(
        mgr, tag="new_tag", content_to_append="initial content",
    )

    block = await mgr.get_core_block()
    assert "initial content" in block


# -------------------- archival_insert --------------------

@pytest.mark.asyncio
async def test_archival_insert_creates_entry():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import archival_insert

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    result = await archival_insert(
        mgr, content="user prefers Hindi UI",
        scope="semantic", tag="preferences",
    )
    assert "Stored" in result

    entries = await mgr.list_all(tier="archival")
    assert len(entries) == 1
    assert entries[0].content == "user prefers Hindi UI"
    assert entries[0].source == "self_edit"


@pytest.mark.asyncio
async def test_archival_insert_requires_content():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import archival_insert

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    with pytest.raises(ValueError, match="content"):
        await archival_insert(mgr, content="")


# -------------------- archival_search --------------------

@pytest.mark.asyncio
async def test_archival_search_returns_matching_facts():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import archival_search

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_archival("user is in Bengaluru")
    await mgr.add_archival("user works at RivaiLabs")
    await mgr.add_archival("weather is sunny today")  # noise

    results = await archival_search(mgr, query="user", limit=5)
    assert len(results) >= 2
    contents = [r["content"] for r in results]
    assert any("Bengaluru" in c for c in contents)
    assert any("RivaiLabs" in c for c in contents)


@pytest.mark.asyncio
async def test_archival_search_returns_dicts_with_metadata():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import archival_search

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_archival(
        "user prefers concise answers",
        tag="preferences", scope="semantic",
    )

    results = await archival_search(mgr, query="concise")
    assert len(results) == 1
    r = results[0]
    assert r["content"] == "user prefers concise answers"
    assert r["tag"] == "preferences"
    assert r["scope"] == "semantic"
    assert "created_at" in r
    assert "id" in r


# -------------------- recall_search --------------------

@pytest.mark.asyncio
async def test_recall_search_only_searches_recall_tier():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import recall_search

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_recall("yesterday user asked about loans")
    await mgr.add_archival("user wants loans")

    results = await recall_search(mgr, query="loans")
    # All results must be from recall tier
    contents = [r["content"] for r in results]
    assert any("yesterday" in c for c in contents)


# -------------------- memory_tool_specs --------------------

def test_memory_tool_specs_returns_five_tools():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import memory_tool_specs

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    specs = memory_tool_specs(mgr)

    names = {s["name"] for s in specs}
    assert names == {
        "core_memory_replace",
        "core_memory_append",
        "archival_insert",
        "archival_search",
        "recall_search",
    }


def test_memory_tool_specs_have_openai_schema_format():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import memory_tool_specs

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    specs = memory_tool_specs(mgr)

    for spec in specs:
        assert "name" in spec
        assert "description" in spec
        assert "parameters" in spec
        assert "callable" in spec
        params = spec["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


@pytest.mark.asyncio
async def test_memory_tool_specs_callables_invoke_real_logic():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import memory_tool_specs

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    specs = memory_tool_specs(mgr)

    # Invoke archival_insert via the spec
    insert_spec = next(s for s in specs if s["name"] == "archival_insert")
    result = await insert_spec["callable"](
        content="learned via tool", tag="learned",
    )
    assert "Stored" in result

    # Invoke archival_search
    search_spec = next(s for s in specs if s["name"] == "archival_search")
    results = await search_spec["callable"](query="learned")
    assert len(results) == 1


# -------------------- register_memory_tools --------------------

def test_register_memory_tools_with_register_tool_api():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import register_memory_tools

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    fake_agent = MagicMock()
    fake_agent.register_tool = MagicMock()

    count = register_memory_tools(fake_agent, mgr)
    assert count == 5
    assert fake_agent.register_tool.call_count == 5


def test_register_memory_tools_with_tools_list():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import register_memory_tools

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")

    class FakeAgent:
        def __init__(self):
            self.tools = []

    agent = FakeAgent()
    count = register_memory_tools(agent, mgr)
    assert count == 5
    assert len(agent.tools) == 5
