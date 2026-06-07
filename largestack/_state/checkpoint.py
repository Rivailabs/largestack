"""Checkpoint/resume — save and restore workflow state."""

from __future__ import annotations
import json, os, sqlite3, time
from typing import Any


class CheckpointManager:
    """Save/restore agent workflow state for crash recovery."""

    def __init__(self, db_path: str = "~/.largestack/checkpoints.db"):
        db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS checkpoints (
            workflow_id TEXT, step_name TEXT, state TEXT,
            created_at REAL, PRIMARY KEY (workflow_id, step_name))""")
        self.db.commit()

    def save(self, workflow_id: str, step: str, state: dict[str, Any]):
        self.db.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?, ?)",
            (workflow_id, step, json.dumps(state, default=str), time.time()),
        )
        self.db.commit()

    def load(self, workflow_id: str, step: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT state FROM checkpoints WHERE workflow_id=? AND step_name=?", (workflow_id, step)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def load_latest(self, workflow_id: str) -> tuple[str, dict[str, Any]] | None:
        row = self.db.execute(
            "SELECT step_name, state FROM checkpoints WHERE workflow_id=? ORDER BY created_at DESC LIMIT 1",
            (workflow_id,),
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def clear(self, workflow_id: str):
        self.db.execute("DELETE FROM checkpoints WHERE workflow_id=?", (workflow_id,))
        self.db.commit()
