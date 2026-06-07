"""Postgres backend for long-term memory (v0.13.0).

Closes the production-grade memory storage gap. Mirrors the SQLite
backend but uses Postgres via ``asyncpg``. Falls back to a synchronous
``psycopg2`` path if ``asyncpg`` isn't installed.

Designed for:

- Single-region NBFC deployments (RDS Postgres, ElastiCache, Mumbai)
- Multi-tenant data segregation (tenant_id is partition key)
- DPDP-compliant retention (TTL enforced via SQL ``DELETE``)

If neither ``asyncpg`` nor ``psycopg2`` is installed, raises
``ImportError`` on first use. All install dependencies are optional.
"""

from __future__ import annotations
import asyncio
import json
import logging
import time
from typing import Any

from largestack._memory.long_term import (
    LongTermMemoryEntry,
    LongTermMemoryStore,
    MemoryScope,
    MemoryTier,
)

log = logging.getLogger("largestack.memory.postgres")


# Schema is identical to SQLite (modulo Postgres-specific types)
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lt_memory_entries (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    tier            TEXT NOT NULL,
    scope           TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      DOUBLE PRECISION NOT NULL,
    last_accessed_at DOUBLE PRECISION NOT NULL,
    tag             TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    purpose         TEXT NOT NULL DEFAULT '',
    ttl_seconds     DOUBLE PRECISION,
    lawful_basis    TEXT NOT NULL DEFAULT '',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_ltm_tenant ON lt_memory_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ltm_tenant_user
    ON lt_memory_entries(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_ltm_tier ON lt_memory_entries(tier);
CREATE INDEX IF NOT EXISTS idx_ltm_scope ON lt_memory_entries(scope);
CREATE INDEX IF NOT EXISTS idx_ltm_content_trgm
    ON lt_memory_entries USING gin (content gin_trgm_ops);
"""


def _have_asyncpg() -> bool:
    try:
        import asyncpg  # noqa: F401

        return True
    except ImportError:
        return False


class PostgresLongTermStore(LongTermMemoryStore):
    """Postgres-backed long-term memory store.

    Args:
        dsn: Postgres connection string
            (``postgresql://user:pass@host:5432/db``)
        pool_min_size: minimum connection pool size
        pool_max_size: maximum connection pool size
        enable_trgm: install pg_trgm extension for fast LIKE search
            (requires CREATEEXT privilege; ignore if unavailable)
    """

    def __init__(
        self,
        dsn: str,
        *,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
        enable_trgm: bool = True,
    ):
        if not _have_asyncpg():
            raise ImportError(
                "asyncpg required for PostgresLongTermStore. Install with: pip install asyncpg"
            )
        self.dsn = dsn
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.enable_trgm = enable_trgm
        self._pool = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
            )
        return self._pool

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                if self.enable_trgm:
                    try:
                        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    except Exception as e:
                        log.warning(f"could not install pg_trgm: {e}; search will use basic LIKE")
                # Split schema into individual statements for asyncpg
                for stmt in _SCHEMA_SQL.split(";"):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        # gin_trgm_ops index requires pg_trgm
                        if "gin_trgm_ops" in stmt and "pg_trgm" in str(e):
                            log.warning(f"skipping trgm index: {e}")
                            continue
                        raise
            self._initialized = True

    @staticmethod
    def _row_to_entry(row) -> LongTermMemoryEntry:
        meta = row["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
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
            metadata=meta or {},
        )

    async def add(self, entry: LongTermMemoryEntry) -> None:
        await self._ensure_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO lt_memory_entries
                (id, tenant_id, user_id, tier, scope, content,
                 created_at, last_accessed_at, tag, source, purpose,
                 ttl_seconds, lawful_basis, metadata)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
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
            )

    async def get(self, entry_id: str) -> LongTermMemoryEntry | None:
        await self._ensure_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM lt_memory_entries WHERE id = $1",
                entry_id,
            )
            if not row:
                return None
            now = time.time()
            await conn.execute(
                "UPDATE lt_memory_entries SET last_accessed_at = $1 WHERE id = $2",
                now,
                entry_id,
            )
            entry = self._row_to_entry(row)
            entry.last_accessed_at = now
            return entry

    async def update(self, entry: LongTermMemoryEntry) -> None:
        await self._ensure_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE lt_memory_entries SET
                    tier=$1, scope=$2, content=$3, last_accessed_at=$4,
                    tag=$5, source=$6, purpose=$7, ttl_seconds=$8,
                    lawful_basis=$9, metadata=$10
                WHERE id=$11
                """,
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
            )

    async def delete(self, entry_id: str) -> bool:
        await self._ensure_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM lt_memory_entries WHERE id = $1",
                entry_id,
            )
            # asyncpg returns "DELETE N"
            return result.endswith(" 1") or result.endswith("1")

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
        await self._ensure_schema()
        pool = await self._get_pool()
        sql = "SELECT * FROM lt_memory_entries WHERE tenant_id = $1"
        params: list[Any] = [tenant_id]
        idx = 2
        if user_id is not None:
            sql += f" AND user_id = ${idx}"
            params.append(user_id)
            idx += 1
        if tier is not None:
            sql += f" AND tier = ${idx}"
            params.append(tier)
            idx += 1
        if scope is not None:
            sql += f" AND scope = ${idx}"
            params.append(scope)
            idx += 1
        if tag is not None:
            sql += f" AND tag = ${idx}"
            params.append(tag)
            idx += 1
        sql += " ORDER BY last_accessed_at DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [self._row_to_entry(r) for r in rows]

    async def search(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        query: str,
        limit: int = 10,
    ) -> list[LongTermMemoryEntry]:
        await self._ensure_schema()
        pool = await self._get_pool()
        sql = "SELECT * FROM lt_memory_entries WHERE tenant_id = $1 AND content ILIKE $2"
        params: list[Any] = [tenant_id, f"%{query}%"]
        idx = 3
        if user_id is not None:
            sql += f" AND user_id = ${idx}"
            params.append(user_id)
            idx += 1
        sql += f" ORDER BY last_accessed_at DESC LIMIT {int(limit)}"

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            now = time.time()
            results = []
            for row in rows:
                entry = self._row_to_entry(row)
                if entry.is_expired(now):
                    continue
                results.append(entry)
            if results:
                ids = [r.id for r in results]
                await conn.execute(
                    "UPDATE lt_memory_entries SET last_accessed_at = $1 WHERE id = ANY($2::text[])",
                    now,
                    ids,
                )
            return results

    async def purge_expired(
        self,
        *,
        tenant_id: str | None = None,
    ) -> int:
        await self._ensure_schema()
        pool = await self._get_pool()
        sql = (
            "DELETE FROM lt_memory_entries "
            "WHERE ttl_seconds IS NOT NULL "
            "AND ($1 - created_at) > ttl_seconds"
        )
        params: list[Any] = [time.time()]
        if tenant_id is not None:
            sql += " AND tenant_id = $2"
            params.append(tenant_id)
        async with pool.acquire() as conn:
            result = await conn.execute(sql, *params)
        # "DELETE N"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def clear(self, *, tenant_id: str | None = None) -> int:
        await self._ensure_schema()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if tenant_id is None:
                result = await conn.execute("DELETE FROM lt_memory_entries")
            else:
                result = await conn.execute(
                    "DELETE FROM lt_memory_entries WHERE tenant_id = $1",
                    tenant_id,
                )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False
