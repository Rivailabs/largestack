"""Database query tool — v0.3.12 hardened.

v0.3.11 had two real defects:

1. The keyword-blocklist was case-sensitive on the unmodified `query.upper()`
   and only checked DROP/DELETE/TRUNCATE/ALTER. INSERT, UPDATE, REPLACE,
   ATTACH, PRAGMA writable_schema were all permitted. An LLM tool call could
   `INSERT INTO users (role) VALUES ('admin')`. Worse, false-positives:
   `SELECT name FROM dropdown` was rejected because "DROP" appeared in the
   uppercased text.

2. `db_path` was LLM-controlled and unrestricted. The LLM could query
   ANY SQLite database the process could read — `~/.largestack/audit.db`,
   `~/.largestack/traces.db`, application secrets, etc.

v0.3.12 fixes:

1. **Statement-type allowlist.** Use `sqlite3` connection in
   `mode=ro&immutable=1` — the database is opened read-only at the SQLite
   level. INSERT/UPDATE/DELETE/PRAGMA writes become operational errors at
   the engine layer. We don't have to maintain a brittle blocklist.

2. **`db_path` allowlisting.** Only paths under `LARGESTACK_DB_TOOL_BASE`
   (default: `cwd/data/`) are accessible. Resolved with `commonpath` so
   path traversal can't escape. Custom DBs require explicit operator
   opt-in via `LARGESTACK_DB_TOOL_ALLOWLIST=path1,path2`.

3. **Result row cap stays at 100** to prevent dump-of-table.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

from largestack._core.tools import tool


def _resolve_db_path(db_path: str) -> tuple[str | None, str | None]:
    """Returns (resolved_path, error_msg). Either is None.

    Allowed if either:
      - path is under LARGESTACK_DB_TOOL_BASE (defaults to cwd/data)
      - path is in LARGESTACK_DB_TOOL_ALLOWLIST (comma-separated absolute paths)
    """
    if not isinstance(db_path, str) or not db_path.strip():
        return None, "db_path must be a non-empty string"

    abs_target = os.path.abspath(os.path.expanduser(db_path))

    # Hard allowlist takes priority
    raw_allow = os.environ.get("LARGESTACK_DB_TOOL_ALLOWLIST", "").strip()
    if raw_allow:
        allowlist = {
            os.path.abspath(os.path.expanduser(p.strip()))
            for p in raw_allow.split(",")
            if p.strip()
        }
        if abs_target in allowlist:
            return abs_target, None
        return None, (
            f"db_path {db_path!r} not in LARGESTACK_DB_TOOL_ALLOWLIST. "
            f"Allowed: {sorted(allowlist)}"
        )

    # Default: cwd/data/
    try:
        cwd = os.getcwd()
    except (FileNotFoundError, OSError):
        # cwd may have been deleted (test fixtures cleaning up tmp dirs)
        cwd = os.path.expanduser("~")
    base = os.path.abspath(
        os.path.expanduser(os.environ.get("LARGESTACK_DB_TOOL_BASE", os.path.join(cwd, "data")))
    )
    try:
        common = os.path.commonpath([abs_target, base])
    except ValueError:
        # Different drives on Windows
        return None, f"db_path {db_path!r} on different volume than LARGESTACK_DB_TOOL_BASE"
    if common != base:
        return None, (
            f"db_path {db_path!r} is outside LARGESTACK_DB_TOOL_BASE ({base}). "
            "Set LARGESTACK_DB_TOOL_ALLOWLIST=<abs path> to permit a specific DB, "
            "or LARGESTACK_DB_TOOL_BASE=<dir> to change the default base directory."
        )
    return abs_target, None


@tool(timeout=10)
async def database_query(query: str, db_path: str = "data/largestack.db") -> str:
    """Execute a read-only SELECT against a SQLite database.

    Safety:
        - The DB is opened in read-only mode (mode=ro). Writes raise an
          error at the engine layer; no need for a brittle keyword blocklist.
        - db_path must be inside LARGESTACK_DB_TOOL_BASE (default: cwd/data/) OR
          be listed in LARGESTACK_DB_TOOL_ALLOWLIST (comma-separated absolute paths).
        - Results capped at 100 rows.

    Args:
        query: SQL query (must be a SELECT or CTE; mutations rejected by RO mode)
        db_path: relative or absolute path; must pass allowlist check

    Returns:
        JSON-encoded list of rows for SELECT, or error message.
    """
    import json

    if not isinstance(query, str) or not query.strip():
        return "Error: query must be a non-empty string"
    if len(query) > 10_000:
        return "Error: query too long (>10KB)"

    resolved, err = _resolve_db_path(db_path)
    if err:
        return f"Request blocked: {err}"

    if not Path(resolved).exists():
        return f"Error: database not found: {db_path}"

    # Read-only URI mode — sqlite3 enforces no writes.
    uri = f"file:{resolved}?mode=ro&immutable=0"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.OperationalError as e:
        return f"Error: cannot open database read-only: {e}"

    conn.row_factory = sqlite3.Row
    try:
        # Strip leading whitespace and require a SELECT/WITH start. Belt-and-
        # suspenders alongside the read-only file mode.
        first_kw = query.lstrip().split(maxsplit=1)[0].upper() if query.lstrip() else ""
        if first_kw not in ("SELECT", "WITH"):
            return (
                f"Error: only SELECT / WITH queries permitted "
                f"(got first keyword: {first_kw!r}). "
                "Mutations are rejected at the SQLite read-only layer regardless."
            )

        try:
            cursor = conn.execute(query)
        except sqlite3.OperationalError as e:
            return f"SQL error: {e}"

        rows = [dict(r) for r in cursor.fetchmany(100)]
        return json.dumps(rows, indent=2, default=str)
    finally:
        conn.close()
