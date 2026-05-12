"""Trace DB migration helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_COLUMNS = {
    "trace_id": "TEXT PRIMARY KEY",
    "timestamp": "REAL",
    "agent": "TEXT",
    "task": "TEXT",
    "model": "TEXT",
    "output": "TEXT",
    "error": "TEXT",
    "duration_ms": "REAL DEFAULT 0",
    "cost": "REAL DEFAULT 0",
    "tokens": "INTEGER DEFAULT 0",
    "turns": "INTEGER DEFAULT 0",
    "finish_reason": "TEXT",
}


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(traces)").fetchall()}


def migrate_trace_db(path: str | Path, *, write: bool = False) -> dict[str, object]:
    p = Path(path).expanduser()
    if write:
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p) if write or p.exists() else sqlite3.connect(":memory:")
    try:
        if write:
            conn.execute("CREATE TABLE IF NOT EXISTS traces (trace_id TEXT PRIMARY KEY)")
        existing = _columns(conn)
        missing = [c for c in REQUIRED_COLUMNS if c not in existing]
        if write:
            for col in missing:
                if col == "trace_id" and not existing:
                    continue
                conn.execute(f"ALTER TABLE traces ADD COLUMN {col} {REQUIRED_COLUMNS[col]}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_agent ON traces(agent)")
            conn.commit()
            existing = _columns(conn)
            missing = [c for c in REQUIRED_COLUMNS if c not in existing]
        return {"path": str(p), "ok": not missing, "missing": missing, "columns": sorted(existing)}
    finally:
        conn.close()


def check_trace_db(path: str | Path) -> dict[str, object]:
    return migrate_trace_db(path, write=False)
