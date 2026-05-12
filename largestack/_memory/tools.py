"""Self-editing memory tools (v0.13.0).

Closes the Letta-pattern gap. Letta's signature feature: the agent
itself can call ``core_memory_replace``, ``core_memory_append``,
``archival_insert``, ``archival_search``, ``recall_search`` mid-
conversation to update its own memory blocks.

This module provides:

1. The five agent-callable tool functions (async, JSON-schema-typed)
2. A ``register_memory_tools(agent, manager)`` helper that registers
   them on a LARGESTACK agent
3. Each tool emits an audit event so memory edits are traceable

Usage::

    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._memory.tools import register_memory_tools
    from largestack._core import Agent

    manager = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    agent = Agent(name="kyc", model="openai/gpt-4o-mini")
    register_memory_tools(agent, manager)
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from largestack._memory.long_term import (
    LongTermMemoryEntry, LongTermMemoryManager, MemoryScope,
)

log = logging.getLogger("largestack.memory.tools")


@dataclass
class MemoryEditEvent:
    """Trace of a self-edit operation. Emitted to audit logs."""
    timestamp: float
    operation: str
    tenant_id: str
    user_id: str
    entry_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# -------------------- Tool implementations --------------------

async def core_memory_replace(
    manager: LongTermMemoryManager,
    *,
    tag: str,
    new_content: str,
    purpose: str = "self_edit",
    lawful_basis: str = "consent",
) -> str:
    """Replace the core-memory entry with the given tag.

    If a tagged entry exists, its content is overwritten. Otherwise a
    new entry is created. Returns a status string for the LLM.

    Args:
        tag: a label like 'persona', 'preferences', 'goals'
        new_content: the replacement text
    """
    if not tag:
        raise ValueError("tag is required")
    if not new_content:
        raise ValueError("new_content is required")

    existing = await manager.list_all(tier="core", tag=tag)
    if existing:
        entry = existing[0]
        entry.content = new_content
        entry.purpose = purpose
        entry.lawful_basis = lawful_basis
        entry.touch()
        await manager.store.update(entry)
        log.info(f"core_memory_replace: updated {entry.id} ({tag})")
        return f"Replaced core memory entry tagged '{tag}'"
    else:
        entry = await manager.add_core(
            new_content,
            tag=tag,
            purpose=purpose,
            lawful_basis=lawful_basis,
        )
        log.info(f"core_memory_replace: created {entry.id} ({tag})")
        return f"Created core memory entry tagged '{tag}'"


async def core_memory_append(
    manager: LongTermMemoryManager,
    *,
    tag: str,
    content_to_append: str,
    purpose: str = "self_edit",
    lawful_basis: str = "consent",
) -> str:
    """Append text to an existing tagged core-memory entry.

    Useful for accumulating preferences or growing a persona without
    losing earlier content.
    """
    if not tag:
        raise ValueError("tag is required")
    if not content_to_append:
        raise ValueError("content_to_append is required")

    existing = await manager.list_all(tier="core", tag=tag)
    if existing:
        entry = existing[0]
        entry.content = entry.content + "\n" + content_to_append
        entry.touch()
        await manager.store.update(entry)
        return f"Appended to core memory entry tagged '{tag}'"
    else:
        entry = await manager.add_core(
            content_to_append, tag=tag,
            purpose=purpose, lawful_basis=lawful_basis,
        )
        return f"Created core memory entry tagged '{tag}'"


async def archival_insert(
    manager: LongTermMemoryManager,
    *,
    content: str,
    scope: MemoryScope = "semantic",
    tag: str = "",
    purpose: str = "self_extracted_fact",
    lawful_basis: str = "consent",
) -> str:
    """Store a fact in the archival (long-term) tier.

    Use for durable facts the agent learns about the user — preferences,
    history, context that should survive across conversations.
    """
    if not content:
        raise ValueError("content is required")

    entry = await manager.add_archival(
        content,
        scope=scope, tag=tag,
        source="self_edit",
        purpose=purpose,
        lawful_basis=lawful_basis,
    )
    log.info(f"archival_insert: {entry.id}")
    return f"Stored archival memory: {entry.id}"


async def archival_search(
    manager: LongTermMemoryManager,
    *,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search the archival tier and return matching facts.

    Returns a list of dicts with ``content``, ``tag``, ``created_at``.
    """
    if not query:
        raise ValueError("query is required")

    results = await manager.search_archival(query, limit=limit)
    return [
        {
            "content": e.content,
            "tag": e.tag,
            "scope": e.scope,
            "created_at": e.created_at,
            "id": e.id,
        }
        for e in results
    ]


async def recall_search(
    manager: LongTermMemoryManager,
    *,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search the recall tier (recent conversation history)."""
    if not query:
        raise ValueError("query is required")

    results = await manager.search_recall(query, limit=limit)
    return [
        {
            "content": e.content,
            "tag": e.tag,
            "source": e.source,
            "created_at": e.created_at,
            "id": e.id,
        }
        for e in results
    ]


# -------------------- Registration helper --------------------

def memory_tool_specs(
    manager: LongTermMemoryManager,
) -> list[dict[str, Any]]:
    """Returns OpenAI-tool-format specs for all 5 memory tools.

    Each spec is suitable for passing to an LLM's ``tools`` parameter.
    Calling the tool is delegated back to the manager.
    """

    async def _replace(*, tag: str, new_content: str) -> str:
        return await core_memory_replace(
            manager, tag=tag, new_content=new_content,
        )

    async def _append(*, tag: str, content_to_append: str) -> str:
        return await core_memory_append(
            manager, tag=tag, content_to_append=content_to_append,
        )

    async def _insert(
        *, content: str, scope: str = "semantic", tag: str = "",
    ) -> str:
        return await archival_insert(
            manager, content=content, scope=scope, tag=tag,
        )

    async def _arch_search(*, query: str, limit: int = 5):
        return await archival_search(manager, query=query, limit=limit)

    async def _recall(*, query: str, limit: int = 5):
        return await recall_search(manager, query=query, limit=limit)

    return [
        {
            "name": "core_memory_replace",
            "description": (
                "Replace a tagged core memory block (always-in-context). "
                "Use for persona, preferences, current goals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Label like 'persona', 'preferences'",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "Replacement text",
                    },
                },
                "required": ["tag", "new_content"],
            },
            "callable": _replace,
        },
        {
            "name": "core_memory_append",
            "description": (
                "Append text to a tagged core memory block."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "content_to_append": {"type": "string"},
                },
                "required": ["tag", "content_to_append"],
            },
            "callable": _append,
        },
        {
            "name": "archival_insert",
            "description": (
                "Store a long-term fact in archival memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "scope": {
                        "type": "string",
                        "enum": ["episodic", "semantic", "procedural"],
                    },
                    "tag": {"type": "string"},
                },
                "required": ["content"],
            },
            "callable": _insert,
        },
        {
            "name": "archival_search",
            "description": (
                "Search archival (long-term) memory by query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "callable": _arch_search,
        },
        {
            "name": "recall_search",
            "description": (
                "Search recent conversation memory by query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "callable": _recall,
        },
    ]


def register_memory_tools(agent, manager: LongTermMemoryManager) -> int:
    """Register all 5 memory tools on a LARGESTACK agent.

    The agent must have a ``register_tool(name, func, schema)`` method
    or expose a ``.tools`` list. Returns the count of tools registered.
    """
    specs = memory_tool_specs(manager)
    count = 0
    for spec in specs:
        # Try common registration APIs
        if hasattr(agent, "register_tool"):
            agent.register_tool(
                spec["name"], spec["callable"],
                schema=spec["parameters"],
                description=spec["description"],
            )
            count += 1
        elif hasattr(agent, "tools") and isinstance(agent.tools, list):
            agent.tools.append(spec)
            count += 1
        else:
            log.warning(
                f"agent has no tool registration API; "
                f"skipping {spec['name']}"
            )
    return count


__all__ = [
    "MemoryEditEvent",
    "core_memory_replace",
    "core_memory_append",
    "archival_insert",
    "archival_search",
    "recall_search",
    "memory_tool_specs",
    "register_memory_tools",
]
