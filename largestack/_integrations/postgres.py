"""Postgres integration — read-only SELECT queries.

Auth: env var ``LARGESTACK_POSTGRES_URL`` (a postgres:// connection string).
Read-only: rejects any non-SELECT/WITH statement. The connection user
should also be created with read-only grants for defense in depth.

Uses asyncpg if available, falls back to psycopg if not.
"""
from __future__ import annotations
import json
import logging
import os

from largestack._core.tools import tool

log = logging.getLogger("largestack.postgres")


def _validate_query(query: str) -> str | None:
    """Returns error string if query is rejected, else None."""
    if not isinstance(query, str) or not query.strip():
        return "query must be a non-empty string"
    if len(query) > 10_000:
        return "query too long (>10KB)"
    first_kw = query.lstrip().split(maxsplit=1)[0].upper() if query.lstrip() else ""
    if first_kw not in ("SELECT", "WITH"):
        return f"only SELECT/WITH queries permitted (got first keyword: {first_kw!r})"
    return None


@tool(timeout=15)
async def postgres_query(query: str, limit: int = 100) -> str:
    """Run a read-only SELECT against a Postgres database.

    Args:
        query: SQL (must start with SELECT or WITH; mutations rejected).
        limit: Max rows returned (default 100, capped at 1000).

    Returns:
        JSON-encoded list of rows, or error string.

    Requires: LARGESTACK_POSTGRES_URL env var. Best practice: connect with a
    read-only user (CREATE ROLE readonly; GRANT SELECT ...) for defense
    in depth even though we already block writes at the query layer.
    """
    url = os.environ.get("LARGESTACK_POSTGRES_URL", "").strip()
    if not url:
        return "Error: LARGESTACK_POSTGRES_URL env var not set."

    err = _validate_query(query)
    if err:
        return f"Request blocked: {err}"

    limit = max(1, min(int(limit), 1000))

    # Try asyncpg first (preferred async driver)
    try:
        import asyncpg
    except ImportError:
        return await _query_via_psycopg(url, query, limit)

    try:
        conn = await asyncpg.connect(url, timeout=10)
    except Exception as e:
        return f"Postgres connection failed: {e}"

    try:
        # asyncpg prepared statements are read-only by default for SELECT
        rows = await conn.fetch(query, timeout=10)
        result = [dict(r) for r in rows[:limit]]
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Postgres query error: {e}"
    finally:
        await conn.close()


async def _query_via_psycopg(url: str, query: str, limit: int) -> str:
    """Fallback to psycopg (sync) if asyncpg isn't installed."""
    try:
        import psycopg
    except ImportError:
        return (
            "Error: needs `pip install asyncpg` (preferred) or `pip install psycopg`"
        )

    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(limit)
                result = [dict(zip(cols, r)) for r in rows]
                return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return f"Postgres error: {e}"
