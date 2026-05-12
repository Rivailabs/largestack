"""SQLite OpenTelemetry span exporter with query interface and retention."""
from __future__ import annotations
import json, os, sqlite3, tempfile, time, logging
from typing import Any

log = logging.getLogger("largestack.observe.sqlite")

try:
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from opentelemetry.sdk.trace import ReadableSpan
    
    class SQLiteSpanExporter(SpanExporter):
        """High-performance SQLite span exporter with WAL mode.
        
        Features:
          - WAL mode: 80K+ inserts/sec, concurrent reads
          - Indexes for fast trace/span lookups
          - Query interface for traces/spans
          - Retention policies (auto-prune old spans)
          - Batch insert optimization
        
            exporter = SQLiteSpanExporter(db_path="~/.largestack/traces.db", retention_days=30)
            
            # Query saved traces
            traces = exporter.query_traces(since=time.time() - 3600, limit=100)
            spans = exporter.get_spans_for_trace(trace_id)
        """
        
        def __init__(self, db_path: str = "~/.largestack/traces.db",
                     retention_days: int = 30, batch_size: int = 100):
            self.db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.retention_days = retention_days
            self.batch_size = batch_size
            
            self.db = sqlite3.connect(self.db_path, check_same_thread=False)
            try:
                self.db.execute("CREATE TABLE IF NOT EXISTS _largestack_trace_write_check (id INTEGER)")
                self.db.execute("DROP TABLE IF EXISTS _largestack_trace_write_check")
                self.db.commit()
            except sqlite3.OperationalError as exc:
                log.warning(
                    "Trace DB %s is not writable (%s); falling back to /tmp",
                    self.db_path,
                    exc,
                )
                try:
                    self.db.close()
                except Exception:
                    pass
                self.db_path = os.path.join(tempfile.gettempdir(), f"largestack-traces-{os.getpid()}.db")
                self.db = sqlite3.connect(self.db_path, check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.execute("PRAGMA cache_size=10000")
            self.db.execute("PRAGMA temp_store=MEMORY")
            
            self.db.execute("""CREATE TABLE IF NOT EXISTS spans (
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                parent TEXT,
                name TEXT NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                duration_ms REAL GENERATED ALWAYS AS ((end_time - start_time) / 1000000.0) STORED,
                attrs TEXT,
                status TEXT,
                events TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (trace_id, span_id)
            )""")
            
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_trace ON spans(trace_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_name ON spans(name)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_start ON spans(start_time)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_created ON spans(created_at)")
            self.db.commit()
            
            # Cleanup on startup (async background would be better)
            self._prune_old_spans()
        
        def export(self, spans):
            """Export a batch of spans to SQLite."""
            try:
                rows = []
                for s in spans:
                    try:
                        events_list = []
                        if hasattr(s, "events") and s.events:
                            events_list = [{
                                "name": e.name,
                                "timestamp": e.timestamp,
                                "attrs": dict(e.attributes or {}),
                            } for e in s.events]
                        
                        rows.append((
                            format(s.context.trace_id, "032x"),
                            format(s.context.span_id, "016x"),
                            format(s.parent.span_id, "016x") if s.parent else None,
                            s.name,
                            s.start_time,
                            s.end_time,
                            json.dumps(dict(s.attributes or {}), default=str),
                            s.status.status_code.name if s.status else "OK",
                            json.dumps(events_list, default=str) if events_list else None,
                        ))
                    except Exception as e:
                        log.warning(f"Failed to serialize span: {e}")
                        continue
                
                if rows:
                    self.db.executemany(
                        "INSERT OR REPLACE INTO spans (trace_id, span_id, parent, name, start_time, end_time, attrs, status, events) VALUES (?,?,?,?,?,?,?,?,?)",
                        rows
                    )
                    self.db.commit()
                
                return SpanExportResult.SUCCESS
            except Exception as e:
                log.error(f"Span export failed: {e}")
                return SpanExportResult.FAILURE
        
        def force_flush(self, timeout_millis: int = 30000) -> bool:
            try:
                self.db.commit()
                return True
            except Exception:
                return False
        
        def shutdown(self):
            try:
                self.db.commit()
                self.db.close()
            except Exception as e:
                log.warning(f"Shutdown error: {e}")
        
        def _prune_old_spans(self):
            """Delete spans older than retention_days."""
            if self.retention_days <= 0:
                return
            try:
                cursor = self.db.execute(
                    "DELETE FROM spans WHERE created_at < datetime('now', ?)",
                    (f"-{self.retention_days} days",)
                )
                deleted = cursor.rowcount
                self.db.commit()
                if deleted > 0:
                    log.info(f"Pruned {deleted} old spans (retention={self.retention_days}d)")
                    self.db.execute("VACUUM")
            except Exception as e:
                log.warning(f"Prune failed: {e}")
        
        # ═══ Query API ═══
        
        def query_traces(self, since: float = None, limit: int = 100,
                         agent_name: str = None) -> list[dict]:
            """Get recent trace roots with aggregate info."""
            since_ns = int(since * 1e9) if since is not None else None
            agent_pattern = f'%"agent_name":"{agent_name}"%' if agent_name else None

            rows = self.db.execute(
                """SELECT trace_id,
                          MIN(start_time) as start_time,
                          MAX(end_time) as end_time,
                          COUNT(*) as span_count,
                          SUM(duration_ms) as total_duration_ms
                   FROM spans
                   WHERE (? IS NULL OR start_time >= ?)
                     AND (? IS NULL OR attrs LIKE ?)
                   GROUP BY trace_id
                   ORDER BY start_time DESC
                   LIMIT ?""",
                (since_ns, since_ns, agent_pattern, agent_pattern, limit),
            ).fetchall()

            return [{
                "trace_id": r[0],
                "start_time": r[1] / 1e9 if r[1] else 0,
                "end_time": r[2] / 1e9 if r[2] else 0,
                "span_count": r[3],
                "total_duration_ms": r[4] or 0,
            } for r in rows]

        def get_spans_for_trace(self, trace_id: str) -> list[dict]:
            """Get all spans in a trace, ordered by start time."""
            rows = self.db.execute(
                "SELECT trace_id, span_id, parent, name, start_time, end_time, "
                "duration_ms, attrs, status, events FROM spans WHERE trace_id=? "
                "ORDER BY start_time",
                (trace_id,)
            ).fetchall()
            
            return [{
                "trace_id": r[0],
                "span_id": r[1],
                "parent": r[2],
                "name": r[3],
                "start_time": r[4] / 1e9 if r[4] else 0,
                "end_time": r[5] / 1e9 if r[5] else 0,
                "duration_ms": r[6],
                "attrs": json.loads(r[7]) if r[7] else {},
                "status": r[8],
                "events": json.loads(r[9]) if r[9] else [],
            } for r in rows]
        
        def get_latency_percentiles(self, span_name: str = None,
                                     since: float = None) -> dict:
            """Get p50/p95/p99 latency for spans."""
            since_ns = int(since * 1e9) if since is not None else None

            rows = self.db.execute(
                """SELECT duration_ms
                   FROM spans
                   WHERE (? IS NULL OR name = ?)
                     AND (? IS NULL OR start_time >= ?)
                   ORDER BY duration_ms""",
                (span_name, span_name, since_ns, since_ns),
            ).fetchall()

            durations = [r[0] for r in rows if r[0] is not None]
            if not durations:
                return {"count": 0}

            def pct(arr, p):
                idx = min(int(len(arr) * p / 100), len(arr) - 1)
                return arr[idx]

            return {
                "count": len(durations),
                "p50": pct(durations, 50),
                "p95": pct(durations, 95),
                "p99": pct(durations, 99),
                "min": durations[0],
                "max": durations[-1],
            }

        def stats(self) -> dict:
            row = self.db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT trace_id) FROM spans"
            ).fetchone()
            return {
                "total_spans": row[0] if row else 0,
                "unique_traces": row[1] if row else 0,
                "db_path": self.db_path,
                "retention_days": self.retention_days,
            }

except ImportError:
    class SQLiteSpanExporter:
        """Fallback when OpenTelemetry is not installed."""
        def __init__(self, *a, **k): pass
        def export(self, spans): pass
        def shutdown(self): pass
        def force_flush(self, timeout_millis: int = 30000) -> bool: return True
        def query_traces(self, *a, **k): return []
        def get_spans_for_trace(self, *a, **k): return []
        def get_latency_percentiles(self, *a, **k): return {}
        @property
        def stats(self): return {"total_spans": 0, "unique_traces": 0}
