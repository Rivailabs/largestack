"""Dashboard REST API — JSON endpoints for React SPA frontend.

v0.3.5 hardening:
- Every /api/* route except /api/health requires X-API-Key (LARGESTACK_DASHBOARD_KEY).
- CORS allowlist read from LARGESTACK_CORS_ALLOWED_ORIGINS env (comma-separated).
  Default in development: localhost variants only. Default in production: empty (deny).
"""
from __future__ import annotations
import json, os, sqlite3, time, logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from largestack._dashboard.auth import verify_api_key
from largestack._dashboard.rate_limit import rate_limit_dependency

log = logging.getLogger("largestack.dashboard.api")


def _resolve_cors_origins() -> list[str]:
    """Resolve allowed CORS origins from env. NEVER returns ['*'] silently."""
    raw = os.environ.get("LARGESTACK_CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if "*" in origins:
            log.warning("LARGESTACK_CORS_ALLOWED_ORIGINS contains '*' — rejected. Use explicit origins.")
            origins = [o for o in origins if o != "*"]
        return origins
    env = os.environ.get("LARGESTACK_ENV", "development").lower()
    if env == "production":
        log.warning(
            "LARGESTACK_CORS_ALLOWED_ORIGINS not set in production — denying all cross-origin. "
            "Set the env var to allow specific frontends."
        )
        return []
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]



def _build_protected_deps():
    """Build the standard protected-route dependency list.

    v0.3.7: optionally appends RBAC enforcement when LARGESTACK_RBAC_ENABLED=1.
    Read-only dashboard routes use the "agent.read" permission.

    v0.3.11: in production, fail-loud if RBAC wiring fails — refuse to
    serve dashboard with authz silently disabled.
    """
    deps = [Depends(verify_api_key), Depends(rate_limit_dependency)]
    if os.environ.get("LARGESTACK_RBAC_ENABLED", "").lower() in ("1", "true", "yes"):
        try:
            from largestack._enterprise.rbac import require_permission, get_default_rbac
            deps.append(Depends(require_permission(get_default_rbac(), "agent.read")))
            log.info("Dashboard API: RBAC enforcement enabled")
        except Exception as e:
            env = os.environ.get("LARGESTACK_ENV", "development").lower()
            if env == "production":
                raise RuntimeError(
                    f"LARGESTACK_RBAC_ENABLED=1 but RBAC wiring failed: {e}. "
                    "Refusing to start dashboard API with authz disabled in production."
                ) from e
            log.warning(f"Dashboard API: RBAC wiring failed: {e}")
    return deps

def create_api() -> FastAPI:
    app = FastAPI(title="LARGESTACK Dashboard API", version="0.1.2")
    
    origins = _resolve_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        max_age=600,
    )
    
    TRACE_DB = os.path.expanduser("~/.largestack/traces.db")
    AUDIT_DB = os.path.expanduser("~/.largestack/audit.db")

    def _q(db_path, sql, params=()):
        if not os.path.exists(db_path): return []
        try:
            db = sqlite3.connect(db_path)
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(sql, params).fetchall()]
        except sqlite3.OperationalError as e:
            # v0.3.11: log at WARNING — silent debug-level swallowing
            # hid the v0.3.10 trace-table mismatch from operators.
            log.warning(f"dashboard query failed (db={db_path}, sql={sql[:80]}): {e}")
            return []
        except Exception as e:
            log.warning(f"dashboard query unexpected error (db={db_path}): {e}")
            return []

    @app.get("/api/overview", dependencies=_build_protected_deps())
    def overview():
        now = time.time()
        traces_24h = _q(TRACE_DB, "SELECT COUNT(*) as n FROM traces WHERE timestamp>?", (now-86400,))
        cost_24h = _q(AUDIT_DB, "SELECT SUM(cost) as c, COUNT(*) as n FROM audit_log WHERE timestamp>?", (now-86400,))
        cost_hourly = _q(AUDIT_DB,
            "SELECT CAST((timestamp-?)/3600 AS INTEGER) as h, SUM(cost) as c, COUNT(*) as n "
            "FROM audit_log WHERE timestamp>? GROUP BY h ORDER BY h",
            (now-86400, now-86400))
        return {
            "traces_24h": traces_24h[0]["n"] if traces_24h else 0,
            "audit_events_24h": (cost_24h[0]["n"] or 0) if cost_24h else 0,
            "total_cost_24h": round((cost_24h[0]["c"] or 0), 4) if cost_24h else 0,
            "cost_hourly": [{"hour": r["h"], "cost": round(r["c"] or 0, 4), "count": r["n"]} for r in cost_hourly],
        }

    @app.get("/api/traces", dependencies=_build_protected_deps())
    def traces(limit: int = 100):
        limit = max(1, min(limit, 1000))
        rows = _q(TRACE_DB, "SELECT * FROM traces ORDER BY timestamp DESC LIMIT ?", (limit,))
        return {"traces": rows}

    @app.get("/api/costs", dependencies=_build_protected_deps())
    def costs(days: int = 7):
        days = max(1, min(days, 365))
        now = time.time()
        # v1.1.1: source cost-by-model from `traces` (audit_log has no model column).
        by_model = _q(TRACE_DB,
            "SELECT model, SUM(cost) as cost, COUNT(*) as calls FROM traces "
            "WHERE timestamp>? AND model IS NOT NULL GROUP BY model ORDER BY cost DESC",
            (now - days * 86400,))
        return {"by_model": by_model, "period_days": days}

    @app.get("/api/agents", dependencies=_build_protected_deps())
    def agents(days: int = 7):
        days = max(1, min(days, 365))
        now = time.time()
        rows = _q(TRACE_DB,
            "SELECT agent, COUNT(*) as runs, AVG(duration_ms) as avg_latency, SUM(cost) as total_cost "
            "FROM traces WHERE timestamp>? GROUP BY agent ORDER BY runs DESC",
            (now - days * 86400,))
        return {"agents": rows}

    @app.get("/api/guards", dependencies=_build_protected_deps())
    def guards():
        # v1.1.1: correct column is event_type (populated when LARGESTACK_AUDIT_EVENTS=1).
        rows = _q(AUDIT_DB,
            "SELECT action as event, COUNT(*) as count FROM audit_log WHERE event_type LIKE 'guard.%' GROUP BY action")
        return {"events": rows}

    @app.get("/api/metrics", dependencies=_build_protected_deps())
    def metrics():
        now = time.time()
        rows = _q(TRACE_DB,
            "SELECT duration_ms FROM traces WHERE timestamp>? ORDER BY duration_ms",
            (now - 86400,))
        durations = sorted([r["duration_ms"] for r in rows if r.get("duration_ms")])
        if not durations:
            return {"count": 0}
        def pct(a, p): return a[min(int(len(a)*p/100), len(a)-1)]
        return {
            "count": len(durations),
            "p50_ms": round(pct(durations, 50), 1),
            "p95_ms": round(pct(durations, 95), 1),
            "p99_ms": round(pct(durations, 99), 1),
            "mean_ms": round(sum(durations)/len(durations), 1),
        }

    @app.get("/api/alerts", dependencies=_build_protected_deps())
    def alerts():
        now = time.time()
        alerts_list = []
        errs = _q(AUDIT_DB, "SELECT COUNT(*) as n FROM audit_log WHERE event_type='agent.run' AND action='failed' AND timestamp>?", (now-3600,))
        if errs and errs[0]["n"] > 10:
            alerts_list.append({"level": "error", "message": f"High error rate: {errs[0]['n']} errors/hour"})
        costs = _q(AUDIT_DB, "SELECT SUM(cost) as c FROM audit_log WHERE timestamp>?", (now-3600,))
        if costs and (costs[0]["c"] or 0) > 10:
            alerts_list.append({"level": "warning", "message": f"High cost: ${costs[0]['c']:.2f}/hour"})
        return {"alerts": alerts_list}

    # Health intentionally public for deployment probes
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.2", "timestamp": time.time()}

    return app
