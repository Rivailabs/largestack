"""Public observability facade for LARGESTACK.

The lower-level package already has traces, metrics, OTEL helpers, adapters,
and dashboard APIs. This facade gives developers one stable, self-hosted API
for run summaries, feedback capture, and lightweight evaluations.
"""
from __future__ import annotations
import json
import os
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from largestack._observe.traces_db import DEFAULT_TRACE_DB, _ensure_schema


@dataclass(frozen=True)
class FeedbackRecord:
    trace_id: str
    rating: int | None = None
    comment: str = ""
    label: str = ""
    metadata: dict[str, Any] | None = None
    created_at: float = 0.0


class Monitor:
    """Small self-hosted monitor for traces, feedback, and run evaluation."""

    def __init__(self, db_path: str | None = None):
        self.db_path = os.path.expanduser(db_path or DEFAULT_TRACE_DB)
        Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        _ensure_schema(self.db_path)
        self._ensure_feedback_schema()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=0.1)

    def _ensure_feedback_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    rating INTEGER,
                    comment TEXT,
                    label TEXT,
                    metadata TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_trace ON feedback(trace_id)")
            conn.commit()

    def list_traces(self, limit: int = 50, agent: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT trace_id, timestamp, agent, task, model, error, duration_ms, cost, tokens, turns, finish_reason FROM traces"
        args: list[Any] = []
        if agent:
            sql += " WHERE agent=?"
            args.append(agent)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        args.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        keys = ["trace_id", "timestamp", "agent", "task", "model", "error", "duration_ms", "cost", "tokens", "turns", "finish_reason"]
        return [dict(zip(keys, row)) for row in rows]

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT trace_id, timestamp, agent, task, model, output, error, duration_ms, cost, tokens, turns, finish_reason FROM traces WHERE trace_id=?",
                (trace_id,),
            ).fetchone()
        if not row:
            return None
        keys = ["trace_id", "timestamp", "agent", "task", "model", "output", "error", "duration_ms", "cost", "tokens", "turns", "finish_reason"]
        return dict(zip(keys, row))

    def record_feedback(
        self,
        trace_id: str,
        *,
        rating: int | None = None,
        comment: str = "",
        label: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FeedbackRecord:
        if rating is not None and not (1 <= int(rating) <= 5):
            raise ValueError("rating must be between 1 and 5")
        rec = FeedbackRecord(
            trace_id=trace_id,
            rating=int(rating) if rating is not None else None,
            comment=comment,
            label=label,
            metadata=metadata or {},
            created_at=time.time(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (trace_id, rating, comment, label, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (rec.trace_id, rec.rating, rec.comment, rec.label, json.dumps(rec.metadata), rec.created_at),
            )
            conn.commit()
        return rec

    def list_feedback(self, trace_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT trace_id, rating, comment, label, metadata, created_at FROM feedback"
        args: list[Any] = []
        if trace_id:
            sql += " WHERE trace_id=?"
            args.append(trace_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        out = []
        for trace_id, rating, comment, label, metadata, created_at in rows:
            out.append({
                "trace_id": trace_id,
                "rating": rating,
                "comment": comment or "",
                "label": label or "",
                "metadata": json.loads(metadata or "{}"),
                "created_at": created_at,
            })
        return out

    def evaluate_trace(self, trace_id: str) -> dict[str, Any]:
        """Return a lightweight quality/ops evaluation for one trace."""
        trace = self.get_trace(trace_id)
        if not trace:
            raise KeyError(f"Trace not found: {trace_id}")
        feedback = self.list_feedback(trace_id=trace_id, limit=100)
        rating_values = [f["rating"] for f in feedback if f.get("rating") is not None]
        avg_rating = sum(rating_values) / len(rating_values) if rating_values else None
        return {
            "trace_id": trace_id,
            "status": "error" if trace.get("error") else "ok",
            "latency_ms": trace.get("duration_ms") or 0,
            "cost": trace.get("cost") or 0,
            "tokens": trace.get("tokens") or 0,
            "feedback_count": len(feedback),
            "average_rating": avg_rating,
            "needs_review": bool(trace.get("error")) or (avg_rating is not None and avg_rating < 3),
        }

    def summary(self, limit: int = 200) -> dict[str, Any]:
        traces = self.list_traces(limit=limit)
        total_cost = sum(float(t.get("cost") or 0.0) for t in traces)
        errors = [t for t in traces if t.get("error")]
        return {
            "traces": len(traces),
            "errors": len(errors),
            "error_rate": (len(errors) / len(traces)) if traces else 0.0,
            "total_cost": total_cost,
            "avg_latency_ms": (sum(float(t.get("duration_ms") or 0.0) for t in traces) / len(traces)) if traces else 0.0,
            "agents": sorted({t.get("agent") for t in traces if t.get("agent")}),
        }


__all__ = ["Monitor", "FeedbackRecord"]
