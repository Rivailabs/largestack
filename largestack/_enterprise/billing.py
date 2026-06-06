"""Usage metering and billing — track tokens, costs, tool calls per user/tenant."""
from __future__ import annotations
import json, logging, os, sqlite3, time
from typing import Any

log = logging.getLogger("largestack.billing")

class UsageMeter:
    """Track detailed usage per user/tenant for billing.
    
    Records: timestamp, user_id, agent, model, input_tokens, output_tokens,
    cost, tool_calls, duration_ms.
    
        meter = UsageMeter(db_path="~/.largestack/usage.db")
        meter.record(user_id="alice", agent="support", model="gpt-4o",
                     input_tokens=500, output_tokens=200, cost=0.012)
        
        summary = meter.get_usage(user_id="alice", since=last_month)
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = ":memory:"
            self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        else:
            self.db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            user_id TEXT NOT NULL,
            tenant_id TEXT,
            agent TEXT,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cached_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0,
            tool_calls INTEGER DEFAULT 0,
            duration_ms REAL,
            metadata TEXT
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_user ON usage(user_id, timestamp)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON usage(tenant_id, timestamp)")
        self.db.commit()
    
    def record(self, user_id: str, input_tokens_or_cost=0, output_tokens: int = 0,
               cost: float = None, model: str = "", agent: str = "",
               tenant_id: str = None, cached_tokens: int = 0, tool_calls: int = 0,
               duration_ms: float = None, metadata: dict = None,
               input_tokens: int = None):
        """Record a single usage event.

        Forms:
          record(user_id, input_tokens, output_tokens, cost)          # legacy positional
          record(user_id, input_tokens=Y, output_tokens=Z, cost=X)    # keyword
        For a cost-only record, pass ``cost=`` explicitly: ``record(user_id, cost=0.9)``.

        v1.1.1: the documented ``input_tokens=`` keyword now works (the parameter was
        previously named ``input_tokens_or_cost`` so the keyword form raised TypeError),
        and a provided cost is never silently dropped (the old float-heuristic branch
        was dead and zeroed ``record(user, 0.9)``).
        """
        # Explicit input_tokens= keyword wins; otherwise the 2nd positional arg.
        if input_tokens is not None:
            input_tokens = int(input_tokens)
        else:
            input_tokens = int(input_tokens_or_cost or 0)
        cost = float(cost) if cost is not None else 0.0

        self.db.execute(
            """INSERT INTO usage (timestamp, user_id, tenant_id, agent, model,
               input_tokens, output_tokens, cached_tokens, cost, tool_calls,
               duration_ms, metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), user_id, tenant_id, agent, model,
             input_tokens, output_tokens, cached_tokens, cost, tool_calls,
             duration_ms, json.dumps(metadata or {}))
        )
        self.db.commit()
    
    def get_usage(self, user_id: str = None, tenant_id: str = None,
                  since: float = None, until: float = None) -> dict:
        """Aggregate usage by filters."""
        row = self.db.execute(
            """SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens),
                      SUM(cached_tokens), SUM(cost), SUM(tool_calls), AVG(duration_ms)
               FROM usage
               WHERE (? IS NULL OR user_id = ?)
                 AND (? IS NULL OR tenant_id = ?)
                 AND (? IS NULL OR timestamp >= ?)
                 AND (? IS NULL OR timestamp <= ?)""",
            (user_id, user_id, tenant_id, tenant_id, since, since, until, until),
        ).fetchone()

        return {
            "request_count": row[0] or 0,
            "requests": row[0] or 0,  # Alias
            "input_tokens": row[1] or 0,
            "output_tokens": row[2] or 0,
            "cached_tokens": row[3] or 0,
            "cost": round(row[4] or 0, 6),
            "total_cost": round(row[4] or 0, 6),  # Backward-compatible alias
            "tool_calls": row[5] or 0,
            "avg_duration_ms": round(row[6] or 0, 2),
        }

    def get_usage_for_current_tenant(self, **kw) -> dict:
        """Auto-scope query to the current tenant (from ContextVar).

        v0.5.0: This is the safe default for multi-tenant SaaS. Operators
        should call this from API handlers instead of get_usage() to avoid
        accidentally leaking other tenants' data when tenant_id is forgotten.

        Raises ValueError if no tenant is set in the current context — which
        is the correct fail-loud behavior in multi-tenant deployments.
        """
        from largestack._enterprise.tenant import _current_tenant_var
        tid = _current_tenant_var.get()
        if not tid:
            raise ValueError(
                "No tenant context set. Use TenantManager.set_current(tid) "
                "before querying, or call get_usage(tenant_id=...) explicitly "
                "if you need to query a specific tenant."
            )
        kw["tenant_id"] = tid
        return self.get_usage(**kw)

    def record_for_current_tenant(self, **kw):
        """Record usage scoped to the current tenant (from ContextVar).

        v0.5.0: prevents accidental cross-tenant billing — if a developer
        forgets to pass tenant_id, this method auto-fills it from context.
        Raises if no tenant context is set.
        """
        from largestack._enterprise.tenant import _current_tenant_var
        tid = _current_tenant_var.get()
        if not tid:
            raise ValueError(
                "No tenant context set. Use TenantManager.set_current(tid) "
                "before recording, or call record(tenant_id=...) explicitly."
            )
        kw["tenant_id"] = tid
        return self.record(**kw)
    
    def get_top_users(self, since: float = None, limit: int = 10) -> list[dict]:
        """Top users by cost."""
        rows = self.db.execute(
            """SELECT user_id, SUM(cost), COUNT(*), SUM(input_tokens + output_tokens)
               FROM usage
               WHERE (? IS NULL OR timestamp >= ?)
               GROUP BY user_id
               ORDER BY SUM(cost) DESC
               LIMIT ?""",
            (since, since, limit),
        ).fetchall()
        return [{"user_id": r[0], "cost": round(r[1], 6), "requests": r[2], "tokens": r[3]} for r in rows]

    def get_by_model(self, since: float = None) -> list[dict]:
        """Cost breakdown by model."""
        rows = self.db.execute(
            """SELECT model, SUM(cost), COUNT(*)
               FROM usage
               WHERE (? IS NULL OR timestamp >= ?)
               GROUP BY model
               ORDER BY SUM(cost) DESC""",
            (since, since),
        ).fetchall()
        return [{"model": r[0], "cost": round(r[1], 6), "requests": r[2]} for r in rows]

class BudgetEnforcer:
    """Enforce monthly/daily budgets per user or tenant."""
    def __init__(self, meter: UsageMeter):
        self.meter = meter
        self._limits: dict[str, dict] = {}  # user_id → {daily, monthly}
    
    def set_limit(self, user_id: str, daily: float = None, monthly: float = None):
        self._limits[user_id] = {"daily": daily, "monthly": monthly}
    
    def check(self, user_id: str) -> tuple[bool, str]:
        """Returns (allowed, reason_if_blocked)."""
        limits = self._limits.get(user_id)
        if not limits: return True, ""
        
        now = time.time()
        if limits.get("daily"):
            daily_usage = self.meter.get_usage(user_id=user_id, since=now - 86400)
            if daily_usage["total_cost"] >= limits["daily"]:
                return False, f"Daily budget exceeded: ${daily_usage['total_cost']:.2f} / ${limits['daily']:.2f}"
        
        if limits.get("monthly"):
            monthly_usage = self.meter.get_usage(user_id=user_id, since=now - 2592000)
            if monthly_usage["total_cost"] >= limits["monthly"]:
                return False, f"Monthly budget exceeded: ${monthly_usage['total_cost']:.2f} / ${limits['monthly']:.2f}"
        
        return True, ""
