"""Event sourcing — immutable event log with snapshots, subscriptions, and projections."""
from __future__ import annotations
import json, sqlite3, os, time, logging, threading
from typing import Any, Callable

log = logging.getLogger("largestack.distributed.event_store")


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
    pass


class EventStore:
    """Append-only event store with snapshots and projections.
    
    Features:
      - Append-only: events are immutable
      - Stream per aggregate: events grouped by stream_id
      - Optimistic concurrency: expected_version check
      - Snapshots: fast state reconstruction for long streams
      - Subscriptions: reactive projection rebuilds
      - Projections: materialized views over events
      - WAL mode for concurrent reads
    
    Usage:
        store = EventStore("~/.largestack/events.db")
        
        # Append events
        v = store.append("order-123", "OrderCreated", {"amount": 100})
        store.append("order-123", "ItemAdded", {"item": "book"}, expected_version=v)
        
        # Reconstruct state
        state = store.reconstruct_state("order-123", reducer=my_reducer)
        
        # Snapshots for fast startup
        store.save_snapshot("order-123", state, version=5)
        
        # Subscribe to new events
        def on_event(event): print(event)
        store.subscribe("order-*", on_event)
    """
    def __init__(self, db_path: str = "~/.largestack/events.db",
                 snapshot_every: int = 100):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.snapshot_every = snapshot_every
        
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            data TEXT NOT NULL,
            metadata TEXT,
            version INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            UNIQUE(stream_id, version)
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_stream ON events(stream_id, version)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(event_type)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
        
        self.db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            stream_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            state TEXT NOT NULL,
            timestamp REAL NOT NULL
        )""")
        self.db.commit()
        
        self._subscribers: list[tuple[str, Callable]] = []  # [(pattern, handler)]
        self._lock = threading.Lock()
    
    def append(self, stream_id: str, event_type: str, data: dict,
               metadata: dict = None, expected_version: int = None) -> int:
        """Append event with optional optimistic concurrency check.
        
        Args:
          expected_version: If provided, append fails if current version != this.
                           Set to 0 for "must not exist".
        
        Returns: new event version
        Raises: ConcurrencyError if expected_version mismatch
        """
        with self._lock:
            row = self.db.execute(
                "SELECT MAX(version) FROM events WHERE stream_id=?",
                (stream_id,)
            ).fetchone()
            current_version = row[0] or 0
            
            if expected_version is not None and current_version != expected_version:
                raise ConcurrencyError(
                    f"Stream {stream_id}: expected version {expected_version}, got {current_version}"
                )
            
            new_version = current_version + 1
            ts = time.time()
            
            try:
                self.db.execute(
                    "INSERT INTO events (stream_id, event_type, data, metadata, version, timestamp) "
                    "VALUES (?,?,?,?,?,?)",
                    (stream_id, event_type,
                     json.dumps(data, default=str),
                     json.dumps(metadata or {}, default=str),
                     new_version, ts)
                )
                self.db.commit()
            except sqlite3.IntegrityError as e:
                raise ConcurrencyError(f"Stream {stream_id} version {new_version} already exists: {e}")
        
        # Fire subscribers
        event = {
            "stream_id": stream_id,
            "type": event_type,
            "data": data,
            "metadata": metadata or {},
            "version": new_version,
            "timestamp": ts,
        }
        self._fire_subscribers(event)
        
        return new_version
    
    def append_batch(self, events: list[dict]) -> list[int]:
        """Append multiple events atomically. Each event: {stream_id, type, data, metadata?}."""
        with self._lock:
            versions = []
            ts = time.time()
            
            # Group by stream for version calculation
            stream_versions: dict[str, int] = {}
            for event in events:
                sid = event["stream_id"]
                if sid not in stream_versions:
                    row = self.db.execute(
                        "SELECT MAX(version) FROM events WHERE stream_id=?",
                        (sid,)
                    ).fetchone()
                    stream_versions[sid] = row[0] or 0
                stream_versions[sid] += 1
                versions.append(stream_versions[sid])
            
            try:
                self.db.executemany(
                    "INSERT INTO events (stream_id, event_type, data, metadata, version, timestamp) "
                    "VALUES (?,?,?,?,?,?)",
                    [(e["stream_id"], e["type"],
                      json.dumps(e["data"], default=str),
                      json.dumps(e.get("metadata", {}), default=str),
                      v, ts)
                     for e, v in zip(events, versions)]
                )
                self.db.commit()
            except sqlite3.IntegrityError as e:
                self.db.rollback()
                raise ConcurrencyError(f"Batch append failed: {e}")
        
        # Fire subscribers for each event
        for event, version in zip(events, versions):
            self._fire_subscribers({
                "stream_id": event["stream_id"],
                "type": event["type"],
                "data": event["data"],
                "metadata": event.get("metadata", {}),
                "version": version,
                "timestamp": ts,
            })
        
        return versions
    
    def get_stream(self, stream_id: str, from_version: int = 0,
                   to_version: int = None) -> list[dict]:
        """Get events for a stream in version range."""
        if to_version is None:
            rows = self.db.execute(
                "SELECT event_type, data, metadata, version, timestamp "
                "FROM events WHERE stream_id=? AND version>? ORDER BY version",
                (stream_id, from_version)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT event_type, data, metadata, version, timestamp "
                "FROM events WHERE stream_id=? AND version>? AND version<=? ORDER BY version",
                (stream_id, from_version, to_version)
            ).fetchall()
        
        return [{
            "type": r[0],
            "data": json.loads(r[1]),
            "metadata": json.loads(r[2]) if r[2] else {},
            "version": r[3],
            "timestamp": r[4],
        } for r in rows]
    
    def get_by_type(self, event_type: str, limit: int = 1000,
                    since: float = None) -> list[dict]:
        """Get all events of a given type across all streams."""
        rows = self.db.execute(
            """SELECT stream_id, event_type, data, metadata, version, timestamp
               FROM events
               WHERE event_type = ?
                 AND (? IS NULL OR timestamp >= ?)
               ORDER BY timestamp DESC
               LIMIT ?""",
            (event_type, since, since, limit),
        ).fetchall()

        return [{
            "stream_id": r[0],
            "type": r[1],
            "data": json.loads(r[2]),
            "metadata": json.loads(r[3]) if r[3] else {},
            "version": r[4],
            "timestamp": r[5],
        } for r in rows]

    def reconstruct_state(self, stream_id: str, reducer: Callable = None,
                           use_snapshot: bool = True) -> dict:
        """Reconstruct state via event replay. Uses snapshot if available.
        
        Args:
          reducer: function(state, event) -> new_state. Defaults to dict merge.
          use_snapshot: If True, start from latest snapshot then replay newer events.
        """
        state = {}
        from_version = 0
        
        if use_snapshot:
            snapshot = self.get_snapshot(stream_id)
            if snapshot:
                state = snapshot["state"]
                from_version = snapshot["version"]
        
        events = self.get_stream(stream_id, from_version=from_version)
        
        if reducer:
            for event in events:
                state = reducer(state, event)
        else:
            # Default: merge event data into state dict
            for event in events:
                if isinstance(event["data"], dict):
                    state.update(event["data"])
        
        return state
    
    def save_snapshot(self, stream_id: str, state: dict, version: int):
        """Save a snapshot for fast state reconstruction."""
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO snapshots (stream_id, version, state, timestamp) "
                "VALUES (?,?,?,?)",
                (stream_id, version, json.dumps(state, default=str), time.time())
            )
            self.db.commit()
    
    def get_snapshot(self, stream_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT version, state, timestamp FROM snapshots WHERE stream_id=?",
            (stream_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "stream_id": stream_id,
            "version": row[0],
            "state": json.loads(row[1]),
            "timestamp": row[2],
        }
    
    def maybe_snapshot(self, stream_id: str, reducer: Callable = None):
        """Auto-snapshot if enough events accumulated since last snapshot."""
        snap = self.get_snapshot(stream_id)
        current_version = self.get_stream_version(stream_id)
        last_snap_version = snap["version"] if snap else 0
        
        if current_version - last_snap_version >= self.snapshot_every:
            state = self.reconstruct_state(stream_id, reducer)
            self.save_snapshot(stream_id, state, current_version)
            return True
        return False
    
    def get_stream_version(self, stream_id: str) -> int:
        row = self.db.execute(
            "SELECT MAX(version) FROM events WHERE stream_id=?",
            (stream_id,)
        ).fetchone()
        return row[0] or 0
    
    def list_streams(self, limit: int = 100) -> list[dict]:
        """List all streams with event counts."""
        rows = self.db.execute(
            "SELECT stream_id, COUNT(*) as cnt, MAX(version) as version, "
            "MAX(timestamp) as last_ts FROM events GROUP BY stream_id "
            "ORDER BY last_ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{
            "stream_id": r[0], "event_count": r[1],
            "version": r[2], "last_timestamp": r[3]
        } for r in rows]
    
    def subscribe(self, stream_pattern: str, handler: Callable):
        """Subscribe to events matching pattern.
        
        Pattern:
          - "order-123": exact stream_id
          - "order-*": wildcard prefix
          - "*": all streams
        """
        self._subscribers.append((stream_pattern, handler))
    
    def _fire_subscribers(self, event: dict):
        sid = event["stream_id"]
        for pattern, handler in self._subscribers:
            if pattern == "*" or sid == pattern or (
                pattern.endswith("*") and sid.startswith(pattern[:-1])
            ):
                try:
                    handler(event)
                except Exception as e:
                    log.error(f"Subscriber {handler} failed: {e}")
    
    @property
    def stats(self) -> dict:
        row = self.db.execute(
            "SELECT COUNT(*), COUNT(DISTINCT stream_id), COUNT(DISTINCT event_type) "
            "FROM events"
        ).fetchone()
        snap_count = self.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        return {
            "total_events": row[0],
            "unique_streams": row[1],
            "unique_event_types": row[2],
            "snapshot_count": snap_count,
            "subscribers": len(self._subscribers),
        }
