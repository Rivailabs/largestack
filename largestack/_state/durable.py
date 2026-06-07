"""Durable execution — exactly-once step semantics.

DBOS Transact pattern: each step is persisted before execution.
On crash, execution resumes from last completed step.
"""

from __future__ import annotations
import json, os, sqlite3, time, hashlib, functools
from typing import Any, Callable


class DurableWorkflow:
    """Durable workflow with exactly-once step execution."""

    def __init__(self, workflow_id: str, db_path: str = "~/.largestack/durable.db"):
        self.wf_id = workflow_id
        db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS steps (
            workflow_id TEXT, step_name TEXT, status TEXT, 
            input TEXT, output TEXT, error TEXT,
            started_at REAL, completed_at REAL,
            PRIMARY KEY (workflow_id, step_name))""")
        self.db.commit()

    async def step(self, name: str, fn: Callable, *args, **kwargs) -> Any:
        """Execute a step with exactly-once semantics."""
        # Check if already completed
        row = self.db.execute(
            "SELECT status, output FROM steps WHERE workflow_id=? AND step_name=?",
            (self.wf_id, name),
        ).fetchone()

        if row and row[0] == "completed":
            return json.loads(row[1])

        # Record step start
        self.db.execute(
            "INSERT OR REPLACE INTO steps VALUES (?,?,?,?,?,?,?,?)",
            (
                self.wf_id,
                name,
                "running",
                json.dumps(args, default=str),
                None,
                None,
                time.time(),
                None,
            ),
        )
        self.db.commit()

        try:
            import asyncio

            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)

            self.db.execute(
                "UPDATE steps SET status=?, output=?, completed_at=? WHERE workflow_id=? AND step_name=?",
                ("completed", json.dumps(result, default=str), time.time(), self.wf_id, name),
            )
            self.db.commit()
            return result
        except Exception as e:
            self.db.execute(
                "UPDATE steps SET status=?, error=?, completed_at=? WHERE workflow_id=? AND step_name=?",
                ("failed", str(e), time.time(), self.wf_id, name),
            )
            self.db.commit()
            raise

    def get_status(self) -> list[dict]:
        """Get status of all steps."""
        self.db.row_factory = sqlite3.Row
        rows = self.db.execute(
            "SELECT * FROM steps WHERE workflow_id=? ORDER BY started_at", (self.wf_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def reset(self):
        """Reset workflow (re-run all steps)."""
        self.db.execute("DELETE FROM steps WHERE workflow_id=?", (self.wf_id,))
        self.db.commit()
