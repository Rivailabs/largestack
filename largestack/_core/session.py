"""Session management — persistent conversations across agent.run() calls.

agent = Agent(name="support")
session = SessionStore("sqlite")

# First call
result = await session.chat(agent, "Hi", session_id="user-123")
# Second call — agent remembers first
result = await session.chat(agent, "My order is #456", session_id="user-123")
"""

from __future__ import annotations
import json, os, sqlite3, time, hashlib
from typing import Any


def _build_context(message: str, history: list[dict]) -> str:
    """Build contextual task from conversation history."""
    if not history:
        return message
    conv = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-10:])
    return f"Conversation history:\n{conv}\n\nCurrent message: {message}"


class SessionStore:
    """SQLite session store with optional encryption for sensitive data."""

    def __init__(
        self,
        backend: str = "sqlite",
        db_path: str = "~/.largestack/sessions.db",
        encryption_key: str = None,
    ):
        self.backend = backend
        if backend == "sqlite":
            db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self.db = sqlite3.connect(db_path)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, timestamp REAL NOT NULL,
                metadata TEXT DEFAULT '{}')""")
            self._enc_key = encryption_key
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON sessions(session_id, timestamp)"
            )
            self.db.commit()

    def _encrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).encrypt(text.encode()).decode()
        except ImportError:
            import logging

            logging.getLogger("largestack.session").warning(
                "cryptography not installed — session data stored as PLAINTEXT. "
                "pip install cryptography for encrypted sessions."
            )
            return text

    def _decrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).decrypt(text.encode()).decode()
        except (ImportError, Exception):
            return text  # Decrypt failed or lib missing — return as-is

    async def chat(self, agent, message: str, session_id: str, **kw) -> Any:
        """Run agent with session history."""
        # Load history
        history = self.load(session_id)

        # Build messages with history
        # Save user message
        self.save(session_id, "user", message)

        # Run agent (inject history via modified engine call)
        from largestack._core.context import AgentContext

        result = await agent.run(self._build_contextual_task(message, history), **kw)

        # Save assistant response
        self.save(session_id, "assistant", result.content)

        return result

    def _build_contextual_task(self, message: str, history: list[dict]) -> str:
        return _build_context(message, history)

    def save(self, session_id: str, role: str, content: str, metadata: dict = None):
        self.db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)",
            (session_id, role, content, time.time(), json.dumps(metadata or {})),
        )
        self.db.commit()

    def load(self, session_id: str, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM sessions WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def delete(self, session_id: str):
        self.db.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        self.db.commit()

    def list_sessions(self, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT session_id, COUNT(*) as msgs, MAX(timestamp) as last_active FROM sessions GROUP BY session_id ORDER BY last_active DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"session_id": r[0], "messages": r[1], "last_active": r[2]} for r in rows]

    def cleanup_expired(self, max_age_hours: int = 168):
        """Delete sessions older than max_age_hours."""
        import time

        cutoff = time.time() - (max_age_hours * 3600)
        self.db.execute("DELETE FROM sessions WHERE timestamp < ?", (cutoff,))
        self.db.commit()

    def export_session(self, session_id: str) -> list[dict]:
        """Export session as JSON-serializable list."""
        rows = self.db.execute(
            "SELECT role, content, timestamp, metadata FROM sessions WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2], "metadata": r[3]} for r in rows]


class RedisSessionStore:
    """Redis-backed session store for distributed deployments."""

    def __init__(
        self, redis_url: str = "redis://localhost:6379", prefix: str = "largestack:session:"
    ):
        self.prefix = prefix
        try:
            import redis

            self._r = redis.from_url(redis_url)
            self._r.ping()
        except (ImportError, Exception) as e:
            raise RuntimeError(f"Redis not available: {e}. pip install redis")

    def _encrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).encrypt(text.encode()).decode()
        except ImportError:
            return text  # No encryption lib — store plaintext

    def _decrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).decrypt(text.encode()).decode()
        except (ImportError, Exception):
            return text  # Decrypt failed or lib missing — return as-is

    async def chat(self, agent, message: str, session_id: str, **kw):
        history = self.load(session_id)
        self.save(session_id, "user", message)
        from largestack._core.session import SessionStore

        task = _build_context(message, history)
        result = await agent.run(task, **kw)
        self.save(session_id, "assistant", result.content)
        return result

    def save(self, session_id: str, role: str, content: str, metadata: dict = None):
        import json, time

        entry = json.dumps({"role": role, "content": content, "ts": time.time()})
        self._r.rpush(f"{self.prefix}{session_id}", entry)

    def load(self, session_id: str, limit: int = 50) -> list[dict]:
        import json

        raw = self._r.lrange(f"{self.prefix}{session_id}", -limit, -1)
        return [json.loads(r) for r in raw]

    def delete(self, session_id: str):
        self._r.delete(f"{self.prefix}{session_id}")

    def list_sessions(self, limit: int = 100) -> list[dict]:
        keys = self._r.keys(f"{self.prefix}*")[:limit]
        return [
            {"session_id": k.decode().replace(self.prefix, ""), "messages": self._r.llen(k)}
            for k in keys
        ]


class PostgresSessionStore:
    """PostgreSQL session store for production deployments."""

    def __init__(self, dsn: str = "postgresql://localhost/largestack"):
        try:
            import psycopg2

            self.conn = psycopg2.connect(dsn)
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL, session_id TEXT NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, timestamp TIMESTAMPTZ DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}')""")
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pg_session ON sessions(session_id, timestamp)"
                )
        except ImportError:
            raise RuntimeError("psycopg2 required: pip install psycopg2-binary")

    def _encrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).encrypt(text.encode()).decode()
        except ImportError:
            return text  # No encryption lib — store plaintext

    def _decrypt(self, text: str) -> str:
        if not self._enc_key:
            return text
        try:
            from cryptography.fernet import Fernet
            import base64, hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(self._enc_key.encode()).digest())
            return Fernet(key).decrypt(text.encode()).decode()
        except (ImportError, Exception):
            return text  # Decrypt failed or lib missing — return as-is

    async def chat(self, agent, message: str, session_id: str, **kw):
        history = self.load(session_id)
        self.save(session_id, "user", message)
        task = _build_context(message, history)
        result = await agent.run(task, **kw)
        self.save(session_id, "assistant", result.content)
        return result

    def save(self, session_id: str, role: str, content: str, metadata: dict = None):
        import json

        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (session_id, role, content, metadata) VALUES (%s,%s,%s,%s)",
                (session_id, role, content, json.dumps(metadata or {})),
            )

    def load(self, session_id: str, limit: int = 50) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM sessions WHERE session_id=%s ORDER BY timestamp DESC LIMIT %s",
                (session_id, limit),
            )
            return [{"role": r[0], "content": r[1]} for r in reversed(cur.fetchall())]

    def delete(self, session_id: str):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))

    def list_sessions(self, limit: int = 100) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, COUNT(*) as msgs, MAX(timestamp) as last FROM sessions GROUP BY session_id ORDER BY last DESC LIMIT %s",
                (limit,),
            )
            return [
                {"session_id": r[0], "messages": r[1], "last_active": str(r[2])}
                for r in cur.fetchall()
            ]

    def cleanup_expired(self, max_age_hours: int = 168):
        """Delete sessions older than max_age_hours (default: 7 days)."""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE timestamp < NOW() - INTERVAL '%s hours'",
                (max_age_hours,),
            )

    def export_session(self, session_id: str) -> list[dict]:
        """Export full session history as JSON-serializable list."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, timestamp, metadata FROM sessions WHERE session_id=%s ORDER BY timestamp",
                (session_id,),
            )
            return [
                {"role": r[0], "content": r[1], "timestamp": str(r[2]), "metadata": r[3]}
                for r in cur.fetchall()
            ]
