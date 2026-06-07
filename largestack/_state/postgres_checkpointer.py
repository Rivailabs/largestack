"""PostgreSQL checkpointer with async connection pooling.

Production-grade durable execution with psycopg3 async pool.
Falls back to SQLite when Postgres unavailable.

Usage:
    cp = PostgresCheckpointer("postgresql://user:pass@host:5432/largestack")
    await cp.save("thread-1", {"step": 5})
    state = await cp.load("thread-1")
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import Any

log = logging.getLogger("largestack.checkpointer.postgres")


class PostgresCheckpointer:
    """Postgres-backed checkpointer with async pool. Production-grade."""

    def __init__(
        self,
        dsn: str | None = None,
        table: str = "largestack_checkpoints",
        pool_min: int = 1,
        pool_max: int = 10,
    ):
        self.dsn = (
            dsn or os.environ.get("LARGESTACK_POSTGRES_DSN") or os.environ.get("DATABASE_URL")
        )
        self.table = table
        self.pool_min = pool_min
        self.pool_max = pool_max
        self._available = False
        self._pool = None
        self._sqlite_mgr = None  # cached SQLite fallback

        if not self.dsn:
            log.warning("PostgresCheckpointer: no DSN, using SQLite fallback")
            return

        try:
            import psycopg
            import psycopg_pool
            from psycopg import sql as psycopg_sql

            self._psycopg = psycopg
            self._sql = psycopg_sql
            self._pool_cls = psycopg_pool.AsyncConnectionPool
            self._available = True
        except ImportError:
            log.warning("psycopg/psycopg_pool not installed. pip install 'psycopg[binary,pool]'")

    async def _ensure_pool(self):
        """Lazy init pool + schema."""
        if self._pool is None and self._available:
            self._pool = self._pool_cls(
                self.dsn, min_size=self.pool_min, max_size=self.pool_max, open=False
            )
            await self._pool.open()
            await self._init_schema()

    async def _init_schema(self):
        sql = self._sql
        table = sql.Identifier(self.table)
        index = sql.Identifier(f"{self.table}_thread_idx")

        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("""
                        CREATE TABLE IF NOT EXISTS {} (
                            thread_id TEXT NOT NULL,
                            checkpoint_id TEXT NOT NULL,
                            state JSONB NOT NULL,
                            metadata JSONB,
                            created_at TIMESTAMPTZ DEFAULT now(),
                            PRIMARY KEY (thread_id, checkpoint_id)
                        )
                    """).format(table)
                )
                await cur.execute(
                    sql.SQL("""
                        CREATE INDEX IF NOT EXISTS {}
                        ON {} (thread_id, created_at DESC)
                    """).format(index, table)
                )
                await conn.commit()

    async def save(
        self,
        thread_id: str,
        state: dict,
        checkpoint_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Save checkpoint async. Returns checkpoint_id."""
        cid = checkpoint_id or f"ck_{int(time.time() * 1000)}"
        if not self._available:
            return self._save_sqlite_fallback(thread_id, state, cid)
        await self._ensure_pool()

        sql = self._sql
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("""
                        INSERT INTO {} (thread_id, checkpoint_id, state, metadata)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (thread_id, checkpoint_id)
                        DO UPDATE SET state = EXCLUDED.state, metadata = EXCLUDED.metadata
                    """).format(sql.Identifier(self.table)),
                    (thread_id, cid, json.dumps(state), json.dumps(metadata or {})),
                )
                await conn.commit()
        return cid

    async def load(self, thread_id: str, checkpoint_id: str | None = None) -> dict | None:
        """Load checkpoint async. None checkpoint_id → latest."""
        if not self._available:
            return self._load_sqlite_fallback(thread_id, checkpoint_id)
        await self._ensure_pool()

        sql = self._sql
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                if checkpoint_id:
                    await cur.execute(
                        sql.SQL("""
                            SELECT state
                            FROM {}
                            WHERE thread_id = %s AND checkpoint_id = %s
                        """).format(sql.Identifier(self.table)),
                        (thread_id, checkpoint_id),
                    )
                else:
                    await cur.execute(
                        sql.SQL("""
                            SELECT state
                            FROM {}
                            WHERE thread_id = %s
                            ORDER BY created_at DESC
                            LIMIT 1
                        """).format(sql.Identifier(self.table)),
                        (thread_id,),
                    )
                row = await cur.fetchone()
                return json.loads(row[0]) if row else None

    async def list_checkpoints(self, thread_id: str, limit: int = 10) -> list[dict]:
        if not self._available:
            return []
        await self._ensure_pool()

        sql = self._sql
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("""
                        SELECT checkpoint_id, created_at, metadata
                        FROM {}
                        WHERE thread_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """).format(sql.Identifier(self.table)),
                    (thread_id, limit),
                )
                rows = await cur.fetchall()
                return [
                    {
                        "checkpoint_id": r[0],
                        "created_at": str(r[1]),
                        "metadata": json.loads(r[2]) if r[2] else {},
                    }
                    for r in rows
                ]

    async def delete_thread(self, thread_id: str) -> int:
        if not self._available:
            return 0
        await self._ensure_pool()

        sql = self._sql
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("DELETE FROM {} WHERE thread_id = %s").format(
                        sql.Identifier(self.table)
                    ),
                    (thread_id,),
                )
                await conn.commit()
                return cur.rowcount

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _get_sqlite_mgr(self):
        """Cached SQLite fallback manager."""
        if self._sqlite_mgr is None:
            from largestack._state.checkpoint import CheckpointManager
            import tempfile

            path = os.environ.get(
                "LARGESTACK_SQLITE_CHECKPOINT",
                os.path.join(tempfile.gettempdir(), "largestack_ckpt.db"),
            )
            self._sqlite_mgr = CheckpointManager(path)
        return self._sqlite_mgr

    def _save_sqlite_fallback(self, thread_id, state, cid):
        mgr = self._get_sqlite_mgr()
        mgr.save(thread_id, cid, state)
        return cid

    def _load_sqlite_fallback(self, thread_id, cid):
        mgr = self._get_sqlite_mgr()
        if cid:
            return mgr.load(thread_id, cid)
        return mgr.load_latest(thread_id)

    @property
    def available(self) -> bool:
        return self._available
