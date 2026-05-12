"""Immutable audit trail with hash chain integrity verification."""
from __future__ import annotations
import hashlib, json, logging, os, sqlite3, time
from typing import Any

log = logging.getLogger("largestack.audit")


class AuditTrail:
    """Append-only audit log with cryptographic integrity chain.
    
    Each entry includes:
      - Timestamp, event_type, agent, user, action, details, cost, trace_id
      - Previous hash (chains all entries)
      - Entry hash (allows integrity verification)
    
    Tampering detection:
      - Any modified/deleted entry breaks the hash chain
      - verify_integrity() walks the chain and reports mismatches
    
    Usage:
        audit = AuditTrail("~/.largestack/audit.db")
        audit.log("agent.run", "execute", agent_name="support", cost=0.05)
        
        # Query
        recent = audit.query(agent_name="support", since=yesterday)
        
        # Integrity check
        ok, broken_id = audit.verify_integrity()
    """
    def __init__(self, db_path: str = "~/.largestack/audit.db", enable_chain: bool = True):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.enable_chain = enable_chain
        
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        
        self.db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        )""")
        
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_name)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_log(trace_id)")
        self.db.commit()
    
    def _compute_hash(self, record: dict) -> str:
        """Compute SHA-256 of a record including prev_hash."""
        # Serialize deterministically
        canonical = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def _get_last_hash(self) -> str:
        row = self.db.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row and row[0] else "GENESIS"
    
    def log(self, event_type: str, action: str, agent_name: str = "",
            user_id: str = "", details: dict = None, cost: float = 0,
            trace_id: str = "", **kwargs):
        """Append entry to audit log with integrity chain."""
        # Allow kwargs to flow into details
        merged_details = dict(details or {})
        merged_details.update(kwargs)
        
        record = {
            "timestamp": time.time(),
            "event_type": event_type,
            "agent_name": agent_name,
            "user_id": user_id,
            "action": action,
            "details": merged_details,
            "cost": float(cost),
            "trace_id": trace_id,
        }
        
        prev_hash = ""
        entry_hash = ""
        if self.enable_chain:
            prev_hash = self._get_last_hash()
            record_for_hash = dict(record)
            record_for_hash["prev_hash"] = prev_hash
            entry_hash = self._compute_hash(record_for_hash)
        
        self.db.execute(
            "INSERT INTO audit_log (timestamp, event_type, agent_name, user_id, action, details, cost, trace_id, prev_hash, entry_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (record["timestamp"], event_type, agent_name, user_id, action,
             json.dumps(merged_details, default=str), cost, trace_id, prev_hash, entry_hash)
        )
        self.db.commit()
    
    def query(self, agent_name: str = None, event_type: str = None,
              user_id: str = None, action: str = None, trace_id: str = None,
              since: float = None, until: float = None, limit: int = 100) -> list[dict]:
        """Query audit log with filters."""
        where = []
        params = []
        if agent_name: where.append("agent_name=?"); params.append(agent_name)
        if event_type: where.append("event_type=?"); params.append(event_type)
        if user_id: where.append("user_id=?"); params.append(user_id)
        if action: where.append("action=?"); params.append(action)
        if trace_id: where.append("trace_id=?"); params.append(trace_id)
        if since: where.append("timestamp>=?"); params.append(since)
        if until: where.append("timestamp<=?"); params.append(until)
        
        sql = "SELECT * FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        self.db.row_factory = sqlite3.Row
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]
    
    def count(self, agent_name: str = None, event_type: str = None,
              user_id: str = None, since: float = None) -> int:
        """Count entries matching filters."""
        where = []
        params = []
        if agent_name: where.append("agent_name=?"); params.append(agent_name)
        if event_type: where.append("event_type=?"); params.append(event_type)
        if user_id: where.append("user_id=?"); params.append(user_id)
        if since: where.append("timestamp>=?"); params.append(since)
        
        sql = "SELECT COUNT(*) FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self.db.execute(sql, params).fetchone()[0]
    
    def verify_integrity(self) -> tuple[bool, int | None]:
        """Walk the hash chain and verify each entry. Returns (ok, broken_id_or_None)."""
        if not self.enable_chain:
            return True, None
        
        self.db.row_factory = sqlite3.Row
        rows = self.db.execute(
            "SELECT * FROM audit_log ORDER BY id"
        ).fetchall()
        
        prev_hash = "GENESIS"
        for row in rows:
            entry = dict(row)
            stored_hash = entry.pop("entry_hash")
            stored_prev = entry.pop("prev_hash")
            eid = entry.pop("id")
            
            # Verify prev_hash matches
            if stored_prev != prev_hash:
                return False, eid
            
            # Recompute hash
            entry["details"] = json.loads(entry["details"]) if entry["details"] else {}
            record = {
                "timestamp": entry["timestamp"],
                "event_type": entry["event_type"],
                "agent_name": entry["agent_name"] or "",
                "user_id": entry["user_id"] or "",
                "action": entry["action"],
                "details": entry["details"],
                "cost": entry["cost"],
                "trace_id": entry["trace_id"] or "",
                "prev_hash": stored_prev,
            }
            computed = self._compute_hash(record)
            
            if computed != stored_hash:
                return False, eid
            
            prev_hash = stored_hash
        
        return True, None
    
    def get_events_for_trace(self, trace_id: str) -> list[dict]:
        """Get all audit entries for a specific trace."""
        return self.query(trace_id=trace_id, limit=1000)
    
    def get_actions_by_user(self, user_id: str, since: float = None) -> dict:
        """Aggregate actions per user."""
        rows = self.db.execute(
            """SELECT action, COUNT(*), SUM(cost)
               FROM audit_log
               WHERE user_id = ?
                 AND (? IS NULL OR timestamp >= ?)
               GROUP BY action
               ORDER BY COUNT(*) DESC""",
            (user_id, since, since),
        ).fetchall()
        return {r[0]: {"count": r[1], "total_cost": round(r[2] or 0, 4)} for r in rows}

    @property
    def stats(self) -> dict:
        row = self.db.execute(
            "SELECT COUNT(*), COUNT(DISTINCT agent_name), COUNT(DISTINCT user_id), SUM(cost) "
            "FROM audit_log"
        ).fetchone()
        return {
            "total_entries": row[0],
            "unique_agents": row[1],
            "unique_users": row[2],
            "total_cost": round(row[3] or 0, 4),
            "integrity_chain_enabled": self.enable_chain,
        }
