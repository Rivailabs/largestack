"""Outbox pattern — atomic state change + event publish, no lost events.

Reference: https://microservices.io/patterns/data/transactional-outbox.html
"""

from __future__ import annotations
import asyncio, json, logging, os, sqlite3, time
from typing import Any, Callable

log = logging.getLogger("largestack.outbox")


class OutboxPattern:
    """Atomic DB update + event publish — survives crashes.

    Pattern:
      1. Write event to outbox table in SAME transaction as business logic
      2. Background worker polls outbox and publishes events
      3. Successful publishes are marked with published=1
      4. Failed publishes retry with exponential backoff
      5. Permanently failed events go to DLQ (dead letter queue)

    Usage:
        outbox = OutboxPattern("~/.largestack/outbox.db")

        # In business transaction
        outbox.write("order.created", {"order_id": "123", "amount": 100})

        # Background worker
        async def publisher(event):
            await kafka.produce(event)

        await outbox.run_worker(publisher)  # runs forever
    """

    def __init__(
        self,
        db_path: str = "~/.largestack/outbox.db",
        max_retries: int = 5,
        retry_base_delay: float = 1.0,
        poll_interval: float = 1.0,
        batch_size: int = 100,
    ):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.poll_interval = poll_interval
        self.batch_size = batch_size

        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")

        self.db.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            aggregate_id TEXT,
            payload TEXT NOT NULL,
            metadata TEXT,
            published INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            published_at REAL,
            next_retry_at REAL
        )""")

        self.db.execute("""CREATE TABLE IF NOT EXISTS outbox_dlq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            last_error TEXT,
            retry_count INTEGER,
            moved_at REAL NOT NULL
        )""")

        self.db.execute("CREATE INDEX IF NOT EXISTS idx_unpub ON outbox(published, next_retry_at)")
        self.db.commit()

        self._running = False
        self._processed_count = 0
        self._failed_count = 0

    def write(
        self, event_type: str, payload: dict, aggregate_id: str = None, metadata: dict = None
    ) -> int:
        """Write event to outbox (should be in same transaction as business logic)."""
        cursor = self.db.execute(
            "INSERT INTO outbox (event_type, aggregate_id, payload, metadata, created_at) "
            "VALUES (?,?,?,?,?)",
            (
                event_type,
                aggregate_id,
                json.dumps(payload, default=str),
                json.dumps(metadata or {}, default=str),
                time.time(),
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def write_batch(self, events: list[dict]) -> list[int]:
        """Batch-write events. Each event: {type, payload, aggregate_id?, metadata?}."""
        ts = time.time()
        cursor = self.db.cursor()
        cursor.executemany(
            "INSERT INTO outbox (event_type, aggregate_id, payload, metadata, created_at) "
            "VALUES (?,?,?,?,?)",
            [
                (
                    e["type"],
                    e.get("aggregate_id"),
                    json.dumps(e["payload"], default=str),
                    json.dumps(e.get("metadata", {}), default=str),
                    ts,
                )
                for e in events
            ],
        )
        self.db.commit()
        # Query for the IDs (executemany doesn't reliably set lastrowid)
        max_row = self.db.execute("SELECT MAX(id) FROM outbox").fetchone()
        last_id = max_row[0] if max_row and max_row[0] is not None else 0
        first_id = last_id - len(events) + 1
        return list(range(first_id, last_id + 1))

    def poll_unpublished(self, limit: int = None) -> list[dict]:
        """Fetch events ready for publishing (not yet published, retry delay elapsed)."""
        limit = limit or self.batch_size
        now = time.time()
        rows = self.db.execute(
            "SELECT id, event_type, aggregate_id, payload, metadata, retry_count "
            "FROM outbox WHERE published=0 AND (next_retry_at IS NULL OR next_retry_at <= ?) "
            "ORDER BY id LIMIT ?",
            (now, limit),
        ).fetchall()
        return [
            {
                "id": r[0],
                "type": r[1],
                "aggregate_id": r[2],
                "payload": json.loads(r[3]),
                "metadata": json.loads(r[4]) if r[4] else {},
                "retry_count": r[5],
            }
            for r in rows
        ]

    def mark_published(self, event_id: int):
        self.db.execute(
            "UPDATE outbox SET published=1, published_at=? WHERE id=?", (time.time(), event_id)
        )
        self.db.commit()

    def mark_failed(self, event_id: int, error: str):
        """Mark as failed with exponential backoff. Moves to DLQ after max_retries."""
        row = self.db.execute(
            "SELECT retry_count, event_type, payload FROM outbox WHERE id=?", (event_id,)
        ).fetchone()
        if not row:
            return
        retry_count = (row[0] or 0) + 1

        if retry_count >= self.max_retries:
            # Move to DLQ
            self.db.execute(
                "INSERT INTO outbox_dlq (original_id, event_type, payload, last_error, retry_count, moved_at) "
                "VALUES (?,?,?,?,?,?)",
                (event_id, row[1], row[2], error, retry_count, time.time()),
            )
            self.db.execute("DELETE FROM outbox WHERE id=?", (event_id,))
            log.warning(f"Event {event_id} moved to DLQ after {retry_count} failures")
            self._failed_count += 1
        else:
            # Exponential backoff
            delay = self.retry_base_delay * (2**retry_count)
            next_retry_at = time.time() + delay
            self.db.execute(
                "UPDATE outbox SET retry_count=?, last_error=?, next_retry_at=? WHERE id=?",
                (retry_count, error[:500], next_retry_at, event_id),
            )

        self.db.commit()

    async def process_once(self, publisher: Callable) -> int:
        """Process one batch. Returns number of events published."""
        events = self.poll_unpublished()
        if not events:
            return 0

        published_count = 0
        for event in events:
            try:
                if asyncio.iscoroutinefunction(publisher):
                    await publisher(event)
                else:
                    publisher(event)
                self.mark_published(event["id"])
                published_count += 1
                self._processed_count += 1
            except Exception as e:
                log.error(f"Publisher failed for event {event['id']}: {e}")
                self.mark_failed(event["id"], str(e))

        return published_count

    async def process(self, publisher: Callable):
        """Alias for process_once (legacy API)."""
        return await self.process_once(publisher)

    async def run_worker(self, publisher: Callable):
        """Run worker loop — process events forever."""
        self._running = True
        while self._running:
            try:
                count = await self.process_once(publisher)
                if count == 0:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                log.error(f"Worker loop error: {e}")
                await asyncio.sleep(self.poll_interval)

    def stop_worker(self):
        self._running = False

    def get_dlq(self, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, original_id, event_type, payload, last_error, retry_count, moved_at "
            "FROM outbox_dlq ORDER BY moved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "original_id": r[1],
                "type": r[2],
                "payload": json.loads(r[3]),
                "last_error": r[4],
                "retry_count": r[5],
                "moved_at": r[6],
            }
            for r in rows
        ]

    def requeue_from_dlq(self, dlq_id: int) -> int | None:
        """Move event back from DLQ to outbox for retry."""
        row = self.db.execute(
            "SELECT event_type, payload FROM outbox_dlq WHERE id=?", (dlq_id,)
        ).fetchone()
        if not row:
            return None
        cursor = self.db.execute(
            "INSERT INTO outbox (event_type, payload, created_at) VALUES (?,?,?)",
            (row[0], row[1], time.time()),
        )
        self.db.execute("DELETE FROM outbox_dlq WHERE id=?", (dlq_id,))
        self.db.commit()
        return cursor.lastrowid

    @property
    def stats(self) -> dict:
        pending = self.db.execute("SELECT COUNT(*) FROM outbox WHERE published=0").fetchone()[0]
        total = self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        dlq_count = self.db.execute("SELECT COUNT(*) FROM outbox_dlq").fetchone()[0]
        return {
            "pending": pending,
            "total_events": total,
            "dlq_size": dlq_count,
            "processed_count": self._processed_count,
            "failed_count": self._failed_count,
            "worker_running": self._running,
        }
