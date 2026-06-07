"""Trace logging for the dashboard (v0.3.11).

v0.3.10 had a 3-way schema mismatch:
  - dashboard SELECTs FROM `traces`
  - sqlite_exporter creates `spans` (OTel-shape)
  - alembic creates `largestack_traces` (Postgres-shape)
  - core/database.py creates `largestack_traces` (different schema again)

The dashboard SELECT statements were silently returning empty results in
every real deployment because no producer wrote to `traces`.

This module is now the **single producer** for the `traces` table that the
dashboard queries. The AgentEngine calls `log_trace()` at the end of every
run. The schema matches every column the dashboard SELECTs:

    timestamp, trace_id, agent, task, model, output, error, duration_ms, cost

The OTel SQLite exporter still produces `spans` for trace-level granularity,
but the dashboard's per-agent-run views read from `traces`.
"""

from __future__ import annotations
import logging
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock

log = logging.getLogger("largestack.traces")

# Single canonical path. Both writer (engine) and reader (dashboard) use this.
DEFAULT_TRACE_DB = os.path.expanduser(
    os.environ.get("LARGESTACK_TRACE_DB", "~/.largestack/traces.db")
)

_init_lock = Lock()
_initialized: set[str] = set()


def _ensure_schema(db_path: str) -> None:
    """Idempotent: create the `traces` table if missing."""
    with _init_lock:
        if db_path in _initialized:
            return
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # Another exporter may already hold the DB while initializing.
                # The table creation below is the critical part; journal mode is
                # an optimization and should not make dashboard traces disappear.
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    agent TEXT NOT NULL,
                    task TEXT,
                    model TEXT,
                    output TEXT,
                    error TEXT,
                    duration_ms REAL DEFAULT 0,
                    cost REAL DEFAULT 0,
                    tokens INTEGER DEFAULT 0,
                    turns INTEGER DEFAULT 0,
                    finish_reason TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_agent ON traces(agent)")
            conn.commit()
            _initialized.add(db_path)
        finally:
            conn.close()


def log_trace(
    *,
    trace_id: str,
    agent: str,
    task: str = "",
    model: str = "",
    output: str = "",
    error: str | None = None,
    duration_ms: float = 0.0,
    cost: float = 0.0,
    tokens: int = 0,
    turns: int = 0,
    finish_reason: str = "stop",
    db_path: str | None = None,
) -> None:
    """Append one trace row. Best-effort — never raises (logs at debug)."""
    db_path = db_path or DEFAULT_TRACE_DB
    try:
        _ensure_schema(db_path)
        conn = sqlite3.connect(db_path, timeout=2.0)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            # v1.1.1: redact secrets from persisted content before writing — the
            # dashboard renders task/output/error, and the logging-only redaction
            # filter never touched the trace DB. Best-effort; never fatal.
            try:
                from largestack._observe.log_redaction import _redact_text as _rx
            except Exception:
                _rx = lambda s: s  # noqa: E731
            # Truncate user-supplied strings — the dashboard renders them.
            conn.execute(
                "INSERT OR REPLACE INTO traces "
                "(trace_id, timestamp, agent, task, model, output, error, "
                "duration_ms, cost, tokens, turns, finish_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace_id,
                    time.time(),
                    str(agent)[:200],
                    _rx(str(task))[:2000] if task else None,
                    str(model)[:100] if model else None,
                    _rx(str(output))[:5000] if output else None,
                    _rx(str(error))[:2000] if error else None,
                    float(duration_ms),
                    float(cost),
                    int(tokens),
                    int(turns),
                    str(finish_reason)[:50],
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.debug(f"trace log failed: {e}")
