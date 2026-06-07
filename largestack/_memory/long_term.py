"""Long-term hierarchical agent memory (v0.12.0).

Closes the Letta / Mem0 / Zep gap. Implements an OS-inspired
hierarchical memory model on top of the existing ``largestack._memory``
primitives:

- **Core memory**: small, always-in-context blocks (persona, user
  preferences, current goals). Always injected into the agent prompt.
- **Recall memory**: searchable conversation history, retrieved by
  similarity when relevant.
- **Archival memory**: long-term semantic facts extracted from
  conversations, stored with provenance + timestamps.

Plus three memory **scopes** (now industry-standard):

- **episodic** — specific past interactions
- **semantic** — facts and preferences
- **procedural** — learned behaviours

Plus **fact extraction** — async LLM-based extraction.

Plus **DPDP-compliant retention** — TTL + purpose + lawful-basis
fields on every entry for India compliance.

This module is namespaced under ``largestack._memory.long_term`` and is
independent of the existing primitives in ``largestack._memory.{buffer,
episodic, semantic, procedural, ...}`` to avoid breaking imports.

Storage backends:

- ``InMemoryLongTermStore`` — default, for testing
- ``SQLiteLongTermStore`` — production for single-node

Both are zero-dep (stdlib only).
"""

from __future__ import annotations
import asyncio
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("largestack.memory.long_term")


# -------------------- Domain types --------------------

MemoryScope = Literal["episodic", "semantic", "procedural"]
MemoryTier = Literal["core", "recall", "archival"]


@dataclass
class LongTermMemoryEntry:
    """A single entry in the hierarchical memory store."""

    id: str
    tenant_id: str
    user_id: str
    tier: MemoryTier
    scope: MemoryScope
    content: str
    created_at: float = field(default_factory=lambda: time.time())
    last_accessed_at: float = field(default_factory=lambda: time.time())
    tag: str = ""
    source: str = ""
    # DPDP — explicit purpose for retention
    purpose: str = ""
    # DPDP — TTL in seconds; ``None`` = retain indefinitely
    ttl_seconds: float | None = None
    # DPDP — lawful basis ("consent", "contract", "legitimate_interest")
    lawful_basis: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        n = now if now is not None else time.time()
        return (n - self.created_at) > self.ttl_seconds

    def touch(self) -> None:
        self.last_accessed_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LongTermMemoryEntry":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class LongTermMemoryStats:
    """Counts of entries per tier + scope."""

    total: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)
    by_scope: dict[str, int] = field(default_factory=dict)
    expired: int = 0


# -------------------- Storage backends --------------------


class LongTermMemoryStore:
    """Abstract storage backend."""

    async def add(self, entry: LongTermMemoryEntry) -> None: ...
    async def get(self, entry_id: str) -> LongTermMemoryEntry | None: ...
    async def update(self, entry: LongTermMemoryEntry) -> None: ...
    async def delete(self, entry_id: str) -> bool: ...
    async def list(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        tier: MemoryTier | None = None,
        scope: MemoryScope | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemoryEntry]: ...
    async def search(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        query: str,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]: ...
    async def purge_expired(
        self,
        *,
        tenant_id: str | None = None,
    ) -> int: ...
    async def clear(self, *, tenant_id: str | None = None) -> int: ...


class InMemoryLongTermStore(LongTermMemoryStore):
    """In-process dict store. Use for tests + small deployments."""

    def __init__(self) -> None:
        self._entries: dict[str, LongTermMemoryEntry] = {}
        self._lock = asyncio.Lock()

    async def add(self, entry: LongTermMemoryEntry) -> None:
        async with self._lock:
            self._entries[entry.id] = entry

    async def get(self, entry_id: str) -> LongTermMemoryEntry | None:
        async with self._lock:
            entry = self._entries.get(entry_id)
            if entry:
                entry.touch()
            return entry

    async def update(self, entry: LongTermMemoryEntry) -> None:
        async with self._lock:
            if entry.id in self._entries:
                self._entries[entry.id] = entry

    async def delete(self, entry_id: str) -> bool:
        async with self._lock:
            return self._entries.pop(entry_id, None) is not None

    async def list(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        tier: MemoryTier | None = None,
        scope: MemoryScope | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemoryEntry]:
        async with self._lock:
            results = []
            for e in self._entries.values():
                if e.tenant_id != tenant_id:
                    continue
                if user_id is not None and e.user_id != user_id:
                    continue
                if tier is not None and e.tier != tier:
                    continue
                if scope is not None and e.scope != scope:
                    continue
                if tag is not None and e.tag != tag:
                    continue
                results.append(e)
            results.sort(key=lambda e: e.last_accessed_at, reverse=True)
            if limit is not None:
                results = results[:limit]
            return results

    async def search(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        query: str,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]:
        """Substring + token-jaccard scoring."""
        async with self._lock:
            q_lower = query.lower()
            q_tokens = set(q_lower.split())

            scored: list[tuple[float, LongTermMemoryEntry]] = []
            for e in self._entries.values():
                if e.tenant_id != tenant_id:
                    continue
                if user_id is not None and e.user_id != user_id:
                    continue
                if e.is_expired():
                    continue
                content_lower = e.content.lower()
                content_tokens = set(content_lower.split())
                score = 0.0
                if q_lower in content_lower:
                    score += 3.0
                if q_tokens and content_tokens:
                    inter = len(q_tokens & content_tokens)
                    union = len(q_tokens | content_tokens)
                    if union:
                        score += inter / union
                if score > 0:
                    scored.append((score, e))

            scored.sort(key=lambda t: t[0], reverse=True)
            results = [e for _, e in scored[:limit]]
            for r in results:
                r.touch()
            return results

    async def purge_expired(self, *, tenant_id: str | None = None) -> int:
        async with self._lock:
            now = time.time()
            to_delete = [
                k
                for k, v in self._entries.items()
                if (tenant_id is None or v.tenant_id == tenant_id) and v.is_expired(now)
            ]
            for k in to_delete:
                del self._entries[k]
            return len(to_delete)

    async def clear(self, *, tenant_id: str | None = None) -> int:
        async with self._lock:
            if tenant_id is None:
                count = len(self._entries)
                self._entries.clear()
                return count
            to_delete = [k for k, v in self._entries.items() if v.tenant_id == tenant_id]
            for k in to_delete:
                del self._entries[k]
            return len(to_delete)


class SQLiteLongTermStore(LongTermMemoryStore):
    """SQLite-backed store. Production-safe for single-node deployments."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS lt_memory_entries (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        tier TEXT NOT NULL,
        scope TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_accessed_at REAL NOT NULL,
        tag TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        purpose TEXT NOT NULL DEFAULT '',
        ttl_seconds REAL,
        lawful_basis TEXT NOT NULL DEFAULT '',
        metadata TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_ltm_tenant
        ON lt_memory_entries(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_ltm_tenant_user
        ON lt_memory_entries(tenant_id, user_id);
    CREATE INDEX IF NOT EXISTS idx_ltm_tier
        ON lt_memory_entries(tier);
    CREATE INDEX IF NOT EXISTS idx_ltm_scope
        ON lt_memory_entries(scope);
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(self.SCHEMA)
        return self._conn

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LongTermMemoryEntry:
        return LongTermMemoryEntry(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            tier=row["tier"],
            scope=row["scope"],
            content=row["content"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            tag=row["tag"],
            source=row["source"],
            purpose=row["purpose"],
            ttl_seconds=row["ttl_seconds"],
            lawful_basis=row["lawful_basis"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    async def add(self, entry: LongTermMemoryEntry) -> None:
        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO lt_memory_entries
                   (id, tenant_id, user_id, tier, scope, content,
                    created_at, last_accessed_at, tag, source, purpose,
                    ttl_seconds, lawful_basis, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry.id,
                    entry.tenant_id,
                    entry.user_id,
                    entry.tier,
                    entry.scope,
                    entry.content,
                    entry.created_at,
                    entry.last_accessed_at,
                    entry.tag,
                    entry.source,
                    entry.purpose,
                    entry.ttl_seconds,
                    entry.lawful_basis,
                    json.dumps(entry.metadata),
                ),
            )

    async def get(self, entry_id: str) -> LongTermMemoryEntry | None:
        async with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT * FROM lt_memory_entries WHERE id = ?",
                (entry_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            entry = self._row_to_entry(row)
            now = time.time()
            conn.execute(
                "UPDATE lt_memory_entries SET last_accessed_at = ? WHERE id = ?",
                (now, entry_id),
            )
            entry.last_accessed_at = now
            return entry

    async def update(self, entry: LongTermMemoryEntry) -> None:
        async with self._lock:
            conn = self._get_conn()
            conn.execute(
                """UPDATE lt_memory_entries SET
                    tier=?, scope=?, content=?, last_accessed_at=?,
                    tag=?, source=?, purpose=?, ttl_seconds=?,
                    lawful_basis=?, metadata=?
                   WHERE id=?""",
                (
                    entry.tier,
                    entry.scope,
                    entry.content,
                    entry.last_accessed_at,
                    entry.tag,
                    entry.source,
                    entry.purpose,
                    entry.ttl_seconds,
                    entry.lawful_basis,
                    json.dumps(entry.metadata),
                    entry.id,
                ),
            )

    async def delete(self, entry_id: str) -> bool:
        async with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM lt_memory_entries WHERE id = ?",
                (entry_id,),
            )
            return cur.rowcount > 0

    async def list(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        tier: MemoryTier | None = None,
        scope: MemoryScope | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[LongTermMemoryEntry]:
        async with self._lock:
            conn = self._get_conn()
            sql = "SELECT * FROM lt_memory_entries WHERE tenant_id = ?"
            params: list[Any] = [tenant_id]
            if user_id is not None:
                sql += " AND user_id = ?"
                params.append(user_id)
            if tier is not None:
                sql += " AND tier = ?"
                params.append(tier)
            if scope is not None:
                sql += " AND scope = ?"
                params.append(scope)
            if tag is not None:
                sql += " AND tag = ?"
                params.append(tag)
            sql += " ORDER BY last_accessed_at DESC"
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
            cur = conn.execute(sql, params)
            return [self._row_to_entry(r) for r in cur.fetchall()]

    async def search(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        query: str,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]:
        async with self._lock:
            conn = self._get_conn()
            sql = "SELECT * FROM lt_memory_entries WHERE tenant_id = ? AND content LIKE ?"
            params: list[Any] = [tenant_id, f"%{query}%"]
            if user_id is not None:
                sql += " AND user_id = ?"
                params.append(user_id)
            sql += f" ORDER BY last_accessed_at DESC LIMIT {int(limit)}"
            cur = conn.execute(sql, params)
            results = []
            now = time.time()
            for row in cur.fetchall():
                entry = self._row_to_entry(row)
                if entry.is_expired(now):
                    continue
                results.append(entry)
            if results:
                conn.executemany(
                    "UPDATE lt_memory_entries SET last_accessed_at = ? WHERE id = ?",
                    [(now, r.id) for r in results],
                )
            return results

    async def purge_expired(self, *, tenant_id: str | None = None) -> int:
        async with self._lock:
            conn = self._get_conn()
            now = time.time()
            sql = (
                "DELETE FROM lt_memory_entries "
                "WHERE ttl_seconds IS NOT NULL "
                "AND (? - created_at) > ttl_seconds"
            )
            params: list[Any] = [now]
            if tenant_id is not None:
                sql += " AND tenant_id = ?"
                params.append(tenant_id)
            cur = conn.execute(sql, params)
            return cur.rowcount

    async def clear(self, *, tenant_id: str | None = None) -> int:
        async with self._lock:
            conn = self._get_conn()
            if tenant_id is None:
                cur = conn.execute("DELETE FROM lt_memory_entries")
            else:
                cur = conn.execute(
                    "DELETE FROM lt_memory_entries WHERE tenant_id = ?",
                    (tenant_id,),
                )
            return cur.rowcount

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# -------------------- Manager --------------------


class LongTermMemoryManager:
    """High-level hierarchical memory manager.

    Args:
        store: a ``LongTermMemoryStore`` (default: ``InMemoryLongTermStore``)
        tenant_id: required for multi-tenancy isolation
        user_id: identifies the end user
        core_block_chars: max chars from core memory injected into prompts
        recall_top_k: how many recall entries to fetch per turn
    """

    def __init__(
        self,
        *,
        store: LongTermMemoryStore | None = None,
        tenant_id: str,
        user_id: str,
        core_block_chars: int = 1500,
        recall_top_k: int = 5,
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required (multi-tenancy)")
        if not user_id:
            raise ValueError("user_id is required")
        self.store = store or InMemoryLongTermStore()
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.core_block_chars = core_block_chars
        self.recall_top_k = recall_top_k

    # -------------------- Add --------------------

    async def add_core(
        self,
        content: str,
        *,
        scope: MemoryScope = "semantic",
        tag: str = "",
        purpose: str = "personalization",
        lawful_basis: str = "consent",
        ttl_seconds: float | None = None,
    ) -> LongTermMemoryEntry:
        entry = LongTermMemoryEntry(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            tier="core",
            scope=scope,
            content=content,
            tag=tag,
            purpose=purpose,
            lawful_basis=lawful_basis,
            ttl_seconds=ttl_seconds,
        )
        await self.store.add(entry)
        return entry

    async def add_recall(
        self,
        content: str,
        *,
        source: str = "conversation",
        scope: MemoryScope = "episodic",
        tag: str = "",
        purpose: str = "personalization",
        lawful_basis: str = "consent",
        ttl_seconds: float | None = 30 * 24 * 3600,
    ) -> LongTermMemoryEntry:
        entry = LongTermMemoryEntry(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            tier="recall",
            scope=scope,
            content=content,
            source=source,
            tag=tag,
            purpose=purpose,
            lawful_basis=lawful_basis,
            ttl_seconds=ttl_seconds,
        )
        await self.store.add(entry)
        return entry

    async def add_archival(
        self,
        content: str,
        *,
        source: str = "extracted",
        scope: MemoryScope = "semantic",
        tag: str = "",
        purpose: str = "personalization",
        lawful_basis: str = "consent",
        ttl_seconds: float | None = None,
    ) -> LongTermMemoryEntry:
        entry = LongTermMemoryEntry(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            tier="archival",
            scope=scope,
            content=content,
            source=source,
            tag=tag,
            purpose=purpose,
            lawful_basis=lawful_basis,
            ttl_seconds=ttl_seconds,
        )
        await self.store.add(entry)
        return entry

    # -------------------- Read --------------------

    async def get_core_block(self) -> str:
        entries = await self.store.list(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            tier="core",
        )
        if not entries:
            return ""
        entries.sort(
            key=lambda e: (0 if e.tag else 1, -e.last_accessed_at),
        )
        out: list[str] = []
        used = 0
        for e in entries:
            if e.is_expired():
                continue
            line = f"- [{e.tag}] {e.content}".strip() if e.tag else f"- {e.content}".strip()
            if used + len(line) + 1 > self.core_block_chars:
                break
            out.append(line)
            used += len(line) + 1
        return "\n".join(out)

    async def search_recall(
        self,
        query: str,
        *,
        limit: int | None = None,
    ) -> list[LongTermMemoryEntry]:
        results = await self.store.search(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            query=query,
            limit=(limit or self.recall_top_k) * 2,
        )
        return [e for e in results if e.tier == "recall"][: (limit or self.recall_top_k)]

    async def search_archival(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]:
        results = await self.store.search(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            query=query,
            limit=limit * 4,
        )
        return [e for e in results if e.tier == "archival"][:limit]

    async def list_all(
        self,
        *,
        tier: MemoryTier | None = None,
        scope: MemoryScope | None = None,
        tag: str | None = None,
    ) -> list[LongTermMemoryEntry]:
        return await self.store.list(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            tier=tier,
            scope=scope,
            tag=tag,
        )

    # -------------------- Maintenance --------------------

    async def stats(self) -> LongTermMemoryStats:
        all_entries = await self.store.list(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )
        s = LongTermMemoryStats(total=len(all_entries))
        now = time.time()
        for e in all_entries:
            s.by_tier[e.tier] = s.by_tier.get(e.tier, 0) + 1
            s.by_scope[e.scope] = s.by_scope.get(e.scope, 0) + 1
            if e.is_expired(now):
                s.expired += 1
        return s

    async def purge_expired(self) -> int:
        return await self.store.purge_expired(tenant_id=self.tenant_id)

    async def forget(self, entry_id: str) -> bool:
        """DPDP right-to-erasure: delete a specific entry.

        Only deletes if the entry belongs to this manager's tenant+user
        (multi-tenancy safety).
        """
        entry = await self.store.get(entry_id)
        if entry is None:
            return False
        if entry.tenant_id != self.tenant_id or entry.user_id != self.user_id:
            return False  # cross-tenant access denied
        return await self.store.delete(entry_id)

    async def forget_user(self) -> int:
        """DPDP right-to-erasure: delete ALL memory for this user."""
        entries = await self.store.list(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )
        count = 0
        for e in entries:
            if await self.store.delete(e.id):
                count += 1
        return count

    # -------------------- Context-window assembly --------------------

    async def build_context(self, query: str) -> str:
        """Assemble a memory context block to inject into agent prompts."""
        sections: list[str] = []

        core = await self.get_core_block()
        if core:
            sections.append(f"## Core Memory (always-in-context)\n{core}")

        recall = await self.search_recall(query)
        if recall:
            now = time.time()
            lines = [f"- {_format_ago(now - e.created_at)}: {e.content}" for e in recall]
            sections.append("## Recent Relevant Memories\n" + "\n".join(lines))

        archival = await self.search_archival(query)
        if archival:
            lines = [f"- {e.content}" for e in archival]
            sections.append("## Long-term Facts\n" + "\n".join(lines))

        return "\n\n".join(sections)


# -------------------- Helpers --------------------


def _format_ago(seconds: float) -> str:
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    if seconds < 86400 * 7:
        return f"{int(seconds // 86400)} days ago"
    if seconds < 86400 * 30:
        return f"{int(seconds // (86400 * 7))} weeks ago"
    return f"{int(seconds // (86400 * 30))} months ago"


# -------------------- Fact extraction --------------------

EXTRACT_FACTS_PROMPT = """\
Extract memorable facts from the conversation turn below. Output a JSON
array of objects, each with keys: ``content`` (a short factual statement),
``scope`` (one of "semantic", "episodic", "procedural"), and ``tag``
(short category like "preferences", "personal", "task").

Only extract facts that would be useful to remember in a future
conversation with the same user. Skip generic statements, jokes, or
fleeting context. Return ``[]`` if nothing memorable.

Turn:
{turn}

JSON output:"""


async def extract_facts(
    judge_runner,
    *,
    turn: str,
    max_facts: int = 5,
) -> list[dict[str, str]]:
    """Use an LLM to extract memorable facts from a conversation turn."""
    prompt = EXTRACT_FACTS_PROMPT.format(turn=turn)
    try:
        resp = await judge_runner.run(prompt)
        content = (getattr(resp, "content", "") or "").strip()
    except Exception as e:
        log.warning(f"fact extraction failed: {e}")
        return []

    if "```" in content:
        import re

        m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)

    try:
        facts = json.loads(content)
    except json.JSONDecodeError:
        log.warning(f"fact extraction returned non-JSON: {content[:200]}")
        return []

    if not isinstance(facts, list):
        return []

    out: list[dict[str, str]] = []
    valid_scopes = {"semantic", "episodic", "procedural"}
    for f in facts[:max_facts]:
        if not isinstance(f, dict):
            continue
        cont = str(f.get("content", "")).strip()
        if not cont:
            continue
        scope = f.get("scope", "semantic")
        if scope not in valid_scopes:
            scope = "semantic"
        tag = str(f.get("tag", "")).strip()[:32]
        out.append({"content": cont, "scope": scope, "tag": tag})
    return out


async def extract_and_store(
    manager: LongTermMemoryManager,
    judge_runner,
    *,
    turn: str,
    tier: MemoryTier = "archival",
    max_facts: int = 5,
    purpose: str = "personalization",
    lawful_basis: str = "consent",
) -> list[LongTermMemoryEntry]:
    """Extract facts from a turn and store them in the given tier."""
    facts = await extract_facts(
        judge_runner,
        turn=turn,
        max_facts=max_facts,
    )
    stored = []
    for f in facts:
        if tier == "core":
            entry = await manager.add_core(
                f["content"],
                scope=f["scope"],
                tag=f["tag"],
                purpose=purpose,
                lawful_basis=lawful_basis,
            )
        elif tier == "recall":
            entry = await manager.add_recall(
                f["content"],
                scope=f["scope"],
                tag=f["tag"],
                source="extracted",
                purpose=purpose,
                lawful_basis=lawful_basis,
            )
        else:
            entry = await manager.add_archival(
                f["content"],
                scope=f["scope"],
                tag=f["tag"],
                source="extracted",
                purpose=purpose,
                lawful_basis=lawful_basis,
            )
        stored.append(entry)
    return stored
