"""Database abstraction — SQLite for dev, PostgreSQL for production.

Usage:
    db = Database.create()  # Auto-detects from LARGESTACK_DATABASE_URL
    db = Database.create("sqlite:///~/.largestack/data.db")
    db = Database.create("postgresql://user:pass@host:5432/largestack")
"""
from __future__ import annotations
import json, logging, os, sqlite3, time
from typing import Any
from contextlib import contextmanager

log = logging.getLogger("largestack.database")


class Database:
    """Unified database interface for SQLite and PostgreSQL."""
    
    def __init__(self, backend: str = "sqlite", connection_string: str = None):
        self.backend = backend
        self.connection_string = connection_string
        self._conn = None
        self._pool = None
    
    @classmethod
    def create(cls, url: str = None) -> "Database":
        """Create database from URL or env var.
        
        v0.3.6: reads in this priority order:
          1. explicit `url` arg
          2. LARGESTACK_DATABASE_URL (canonical)
          3. LARGESTACK_POSTGRES_DSN (alias — used by docker-compose.yml)
          4. SQLite default at ~/.largestack/data.db
        
        Logs a warning if LARGESTACK_POSTGRES_DSN is set without LARGESTACK_DATABASE_URL
        so the env var name mismatch is visible.
        """
        if url is None:
            url = os.environ.get("LARGESTACK_DATABASE_URL")
            if url is None:
                # Fall back to the docker-compose env var name
                dsn_alias = os.environ.get("LARGESTACK_POSTGRES_DSN")
                if dsn_alias:
                    log.warning(
                        "LARGESTACK_POSTGRES_DSN is set but LARGESTACK_DATABASE_URL is not. "
                        "Using LARGESTACK_POSTGRES_DSN as the database URL. "
                        "Recommend setting LARGESTACK_DATABASE_URL to standardize."
                    )
                    url = dsn_alias
                else:
                    url = "sqlite:///~/.largestack/data.db"
        
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            return PostgreSQLDatabase(url)
        else:
            path = url.replace("sqlite:///", "")
            return SQLiteDatabase(path)
    
    def execute(self, sql: str, params: tuple = ()) -> Any:
        raise NotImplementedError
    
    def executemany(self, sql: str, params_list: list) -> Any:
        raise NotImplementedError
    
    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        raise NotImplementedError
    
    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        raise NotImplementedError
    
    def commit(self):
        raise NotImplementedError
    
    def close(self):
        raise NotImplementedError
    
    @contextmanager
    def transaction(self):
        """Context manager for atomic transactions."""
        raise NotImplementedError
    
    @property
    def placeholder(self) -> str:
        """Parameter placeholder: ? for SQLite, %s for PostgreSQL."""
        return "?"


class SQLiteDatabase(Database):
    """SQLite backend with WAL mode."""
    
    def __init__(self, path: str = "~/.largestack/data.db"):
        super().__init__("sqlite")
        self.path = os.path.expanduser(path)
        # Handle :memory: and skip makedirs for in-memory or paths without dir
        if self.path != ":memory:":
            dir_part = os.path.dirname(self.path)
            if dir_part:
                os.makedirs(dir_part, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
    
    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql, params)
    
    def executemany(self, sql: str, params_list: list):
        return self._conn.executemany(sql, params_list)
    
    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    
    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]
    
    def commit(self):
        self._conn.commit()
    
    def close(self):
        self._conn.close()
    
    @contextmanager
    def transaction(self):
        try:
            yield self
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
    
    @property
    def placeholder(self) -> str:
        return "?"


class PostgreSQLDatabase(Database):
    """PostgreSQL backend with connection pooling."""
    
    def __init__(self, url: str):
        super().__init__("postgresql", url)
        self._pool = None
        self._conn = None
        # Connect lazily so configuration/factory tests and startup checks can
        # verify routing without requiring DNS/network access immediately.

    
    def _connect(self):
        try:
            import psycopg2
            import psycopg2.extras
            self._conn = psycopg2.connect(self.connection_string)
            self._conn.autocommit = False
            log.info("PostgreSQL: connected")
        except ImportError:
            try:
                import psycopg
                self._conn = psycopg.connect(self.connection_string)
                self._conn.autocommit = False
                log.info("PostgreSQL (psycopg3): connected")
            except ImportError:
                raise ImportError(
                    "PostgreSQL requires psycopg2 or psycopg3: "
                    "pip install psycopg2-binary  OR  pip install psycopg[binary]"
                )
    
    def _ensure_connection(self):
        if self._conn is None:
            self._connect()

    def execute(self, sql: str, params: tuple = ()):
        self._ensure_connection()
        sql = self._convert_placeholders(sql)
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        return cursor
    
    def executemany(self, sql: str, params_list: list):
        self._ensure_connection()
        sql = self._convert_placeholders(sql)
        cursor = self._conn.cursor()
        cursor.executemany(sql, params_list)
        return cursor
    
    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        self._ensure_connection()
        sql = self._convert_placeholders(sql)
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    
    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        self._ensure_connection()
        sql = self._convert_placeholders(sql)
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    def commit(self):
        self._ensure_connection()
        self._conn.commit()
    
    def close(self):
        if self._conn:
            self._conn.close()
    
    @contextmanager
    def transaction(self):
        self._ensure_connection()
        try:
            yield self
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
    
    @property
    def placeholder(self) -> str:
        return "%s"
    
    @staticmethod
    def _convert_placeholders(sql: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL %s."""
        result = []
        in_string = False
        quote_char = None
        for char in sql:
            if char in ("'", '"') and not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char and in_string:
                in_string = False
            
            if char == "?" and not in_string:
                result.append("%s")
            else:
                result.append(char)
        return "".join(result)


# ═══ Migration helpers ═══

MIGRATIONS = {
    "001_core_tables": """
        CREATE TABLE IF NOT EXISTS largestack_traces (
            trace_id TEXT PRIMARY KEY,
            agent_name TEXT,
            task TEXT,
            status TEXT DEFAULT 'completed',
            total_cost REAL DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            duration_ms REAL DEFAULT 0,
            turns INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS largestack_audit_log (
            id SERIAL PRIMARY KEY,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            agent_name TEXT,
            user_id TEXT,
            action TEXT NOT NULL,
            details TEXT,
            cost REAL DEFAULT 0,
            trace_id TEXT,
            prev_hash TEXT,
            entry_hash TEXT
        );
        
        CREATE TABLE IF NOT EXISTS largestack_licenses (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            plan TEXT NOT NULL,
            tier TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            max_agents INTEGER DEFAULT 3,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            payment_provider TEXT,
            payment_id TEXT
        );
        
        CREATE TABLE IF NOT EXISTS largestack_usage (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            tenant_id TEXT,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0,
            timestamp REAL NOT NULL
        );
    """,
}


def run_migrations(db: Database):
    """Run all pending migrations."""
    # Create migrations tracking table
    if db.backend == "sqlite":
        db.execute("""CREATE TABLE IF NOT EXISTS largestack_migrations (
            name TEXT PRIMARY KEY, applied_at REAL NOT NULL)""")
    else:
        db.execute("""CREATE TABLE IF NOT EXISTS largestack_migrations (
            name TEXT PRIMARY KEY, applied_at DOUBLE PRECISION NOT NULL)""")
    db.commit()
    
    for name, sql in MIGRATIONS.items():
        existing = db.fetchone("SELECT name FROM largestack_migrations WHERE name=?", (name,))
        if existing:
            continue
        
        # Execute migration
        for statement in sql.strip().split(";"):
            statement = statement.strip()
            if statement:
                # Adapt SERIAL for SQLite
                if db.backend == "sqlite":
                    statement = statement.replace("SERIAL", "INTEGER")
                db.execute(statement)
        
        db.execute("INSERT INTO largestack_migrations (name, applied_at) VALUES (?, ?)",
                   (name, time.time()))
        db.commit()
        log.info(f"Migration applied: {name}")
