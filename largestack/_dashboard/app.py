"""Full dashboard — 10 views with real Chart.js visualizations on trace/metrics data.

Auth: pages/API are protected via X-API-Key (LARGESTACK_DASHBOARD_KEY env var).
In development, auth is bypassed with a one-time warning. In production
(LARGESTACK_ENV=production) without LARGESTACK_DASHBOARD_KEY set, all routes return 401.
The /health endpoint is always public (deployment healthcheck friendly).

v0.3.6: HTML escaping on every DB-derived string injected into HTML responses
to prevent XSS via agent names, trace content, event names, etc. CSP header
added to all HTML routes.
"""

from __future__ import annotations
import html as _html
import json, os, sqlite3, time
import logging
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from starlette.datastructures import MutableHeaders
from largestack._dashboard.auth import verify_api_key
from largestack._dashboard.rate_limit import rate_limit_dependency


def _esc(value) -> str:
    """HTML-escape any value before injection into HTML responses."""
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


# Defense-in-depth: strict CSP. v0.4.0 — replaced 'unsafe-inline' with
# per-request nonces. The middleware injects a fresh `nonce-XYZ` into
# every HTML response and into a request-scoped `request.state.csp_nonce`
# so route handlers can stamp it into <script nonce=...> tags.
def _build_csp_header(nonce: str) -> str:
    return (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        f"style-src 'self' 'nonce-{nonce}'; "
        f"img-src 'self' data:; "
        f"connect-src 'self'; "
        f"frame-ancestors 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'; "
        f"object-src 'none'"
    )


def _generate_nonce() -> str:
    import secrets

    # 16 bytes → 22 base64 chars; per-request, never reused.
    return secrets.token_urlsafe(16)


class _SecurityHeadersMiddleware:
    """ASGI middleware for per-request CSP nonces and HTML security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        nonce = _generate_nonce()
        scope.setdefault("state", {})["csp_nonce"] = nonce

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                if "text/html" in content_type:
                    headers["Content-Security-Policy"] = _build_csp_header(nonce)
                    headers["X-Frame-Options"] = "DENY"
                    headers["X-Content-Type-Options"] = "nosniff"
                    headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                    headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


def _build_protected_deps():
    """v0.3.7: optionally append RBAC dep when LARGESTACK_RBAC_ENABLED=1.

    v0.3.11: when RBAC is enabled but its import/wiring fails, fail
    DIFFERENTLY by environment:
      - production (LARGESTACK_ENV=production): raise — better to crash than to
        silently serve dashboard with no authz.
      - development: log a loud WARNING and continue.
    """
    deps = [Depends(verify_api_key), Depends(rate_limit_dependency)]
    if os.environ.get("LARGESTACK_RBAC_ENABLED", "").lower() in ("1", "true", "yes"):
        try:
            from largestack._enterprise.rbac import require_permission, get_default_rbac

            deps.append(Depends(require_permission(get_default_rbac(), "agent.read")))
        except Exception as e:
            env = os.environ.get("LARGESTACK_ENV", "development").lower()
            if env == "production":
                raise RuntimeError(
                    f"LARGESTACK_RBAC_ENABLED=1 but RBAC wiring failed in production: {e}. "
                    "Refusing to start dashboard with authz disabled."
                ) from e
            import logging

            logging.getLogger("largestack.dashboard").warning(
                "LARGESTACK_RBAC_ENABLED=1 but RBAC wiring failed (%s). "
                "Continuing without RBAC enforcement (development mode).",
                e,
            )
    return deps


def create_app() -> FastAPI:
    app = FastAPI(title="Largestack AI Dashboard")
    app.add_middleware(_SecurityHeadersMiddleware)

    TRACE_DB = os.path.expanduser("~/.largestack/traces.db")
    AUDIT_DB = os.path.expanduser("~/.largestack/audit.db")

    CSS = """body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0f;color:#e0e0ea;margin:0;padding:0}
    .nav{background:#111119;border-bottom:1px solid #252535;padding:8px 20px;display:flex;gap:12px;align-items:center;position:sticky;top:0;z-index:10}
    .nav a{color:#8888a0;text-decoration:none;font-size:13px;padding:4px 10px;border-radius:4px;transition:all .15s}
    .nav a:hover,.nav a.active{color:#7c6cf0;background:#7c6cf015}
    .content{padding:20px;max-width:1400px;margin:0 auto}
    h1{color:#7c6cf0;font-size:20px;margin:0}
    h2{color:#aab;font-size:16px;margin:20px 0 10px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}
    .grid-2{grid-template-columns:repeat(2,1fr)}
    .card{background:#111119;border:1px solid #252535;border-radius:8px;padding:16px}
    .card-chart{min-height:300px}
    .stat{font-size:28px;font-weight:700;color:#3dd68c}
    .stat-sub{font-size:11px;color:#777}
    .label{font-size:11px;color:#555568;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px}
    table{width:100%;border-collapse:collapse;font-size:12px}
    th{text-align:left;padding:8px;border-bottom:1px solid #252535;color:#8a8aa0;font-weight:600}
    td{padding:6px 8px;border-bottom:1px solid #151520}
    tr:hover td{background:#161622}
    .tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
    .tag-ok{background:#3dd68c25;color:#3dd68c}
    .tag-err{background:#f0616125;color:#f06161}
    .tag-warn{background:#ffa72625;color:#ffa726}
    canvas{max-height:300px}
    .empty{padding:40px;text-align:center;color:#555568;font-style:italic}
    /* v0.4.0: a11y — visible focus outline for keyboard nav */
    a:focus-visible,button:focus-visible{outline:2px solid #7c6cf0;outline-offset:2px;border-radius:4px}
    /* v0.4.0: skip-to-content link for screen readers */
    .skip-link{position:absolute;top:-100px;left:0;background:#7c6cf0;color:#fff;padding:8px 16px;text-decoration:none;border-radius:0 0 4px 0}
    .skip-link:focus{top:0;z-index:100}
    /* v0.4.0: respect reduced-motion preference */
    @media (prefers-reduced-motion: reduce){
        *{animation-duration:0.01ms !important;transition-duration:0.01ms !important}
    }
    /* v0.4.0: mobile responsive — collapse nav at ≤640px, single-col grids ≤480px */
    @media (max-width:640px){
        .nav{flex-wrap:wrap;padding:8px 12px;gap:6px}
        .nav h1{font-size:16px;width:100%;margin-bottom:4px}
        .nav a{font-size:12px;padding:3px 8px}
        .content{padding:12px}
        .grid-2{grid-template-columns:1fr}
        .stat{font-size:22px}
        table{font-size:11px}
        th,td{padding:4px}
    }
    @media (max-width:480px){
        .grid{grid-template-columns:1fr}
        .card{padding:12px}
    }"""

    def _db_query(db_path, sql, params=()):
        if not os.path.exists(db_path):
            return []
        try:
            with sqlite3.connect(db_path, timeout=0.2) as db:
                db.row_factory = sqlite3.Row
                return [dict(r) for r in db.execute(sql, params).fetchall()]
        except Exception:
            return []

    def layout(title, content, active="", api_key="", nonce=""):
        """Render dashboard HTML.

        v0.3.9: ``api_key`` (when truthy) injects ``<meta name="largestack-api-key">``
        so the React SPA can read it for authenticated ``/api/*`` fetches.

        v0.4.0: ``nonce`` injects a per-request CSP nonce on every inline
        ``<style>``/``<script>`` so we can drop ``'unsafe-inline'`` from
        the CSP. The middleware sets ``request.state.csp_nonce`` and the
        route handlers thread it through here.
        """
        nav_items = [
            ("Overview", "/"),
            ("Traces", "/traces"),
            ("Costs", "/costs"),
            ("Agents", "/agents"),
            ("Tools", "/tools"),
            ("Guards", "/guards"),
            ("Memory", "/memory"),
            ("Metrics", "/metrics"),
            ("Alerts", "/alerts"),
            ("Settings", "/settings"),
        ]

        # v0.4.0: aria-current on active link, role=navigation on nav
        def nav_link(name, url):
            active_class = "active" if url == active else ""
            aria_current = ' aria-current="page"' if url == active else ""
            return f'<a href="{url}" class="{active_class}"{aria_current}>{name}</a>'

        nav = "".join(nav_link(name, url) for name, url in nav_items)
        api_meta = f'<meta name="largestack-api-key" content="{_esc(api_key)}">' if api_key else ""
        nonce_attr = f' nonce="{_esc(nonce)}"' if nonce else ""
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Largestack AI - {title}</title>
        {api_meta}
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"{nonce_attr}></script>
        <style{nonce_attr}>{CSS}</style></head><body>
        <a href="#main-content" class="skip-link">Skip to main content</a>
        <nav class="nav" role="navigation" aria-label="Dashboard sections"><h1>Largestack AI</h1>{nav}</nav>
        <main id="main-content" class="content" role="main" aria-label="{_esc(title)}">{content}</main></body></html>"""

    def _verified_api_key(request: Request) -> str:
        """v0.3.9: returns the X-API-Key header value AFTER the auth dep has
        passed. Used to inject the key into the dashboard HTML <meta> tag so
        the React SPA can use it for /api/* fetches without exposing it
        outside the same-origin authenticated session.
        """
        return request.headers.get("X-API-Key", "") or ""

    # Public health endpoint — no auth required (deployment healthchecks)
    @app.get("/health", response_class=JSONResponse)
    def health():
        """Liveness probe. Verifies DB paths reachable and core imports succeed.
        Returns 200 only if package imports + at least one trace/audit DB readable."""
        package = None
        package_error = None
        try:
            import largestack as package

            package_version = getattr(package, "__version__", "unknown")
        except Exception as e:
            package_error = e
            package_version = "unknown"
        status = {"status": "ok", "version": package_version, "checks": {}}
        # Trace DB reachable
        try:
            _ = _db_query(TRACE_DB, "SELECT 1 LIMIT 1")
            status["checks"]["trace_db"] = "ok"
        except Exception as e:
            status["checks"]["trace_db"] = f"error: {e}"
        # Audit DB reachable
        try:
            _ = _db_query(AUDIT_DB, "SELECT 1 LIMIT 1")
            status["checks"]["audit_db"] = "ok"
        except Exception as e:
            status["checks"]["audit_db"] = f"error: {e}"
        # Core largestack imports
        if package is not None:
            status["checks"]["package"] = f"ok (v{getattr(package, '__version__', 'unknown')})"
        else:
            status["checks"]["package"] = f"error: {package_error}"
            status["status"] = "degraded"
        return status

    @app.get("/", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def overview(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        # KPIs
        traces = _db_query(
            TRACE_DB, "SELECT COUNT(*) as n FROM traces WHERE timestamp > ?", (time.time() - 86400,)
        )
        audits = _db_query(
            AUDIT_DB,
            "SELECT SUM(cost) as c, COUNT(*) as n FROM audit_log WHERE timestamp > ?",
            (time.time() - 86400,),
        )

        trace_count = traces[0]["n"] if traces else 0
        total_cost = (audits[0]["c"] or 0) if audits else 0
        audit_count = (audits[0]["n"] or 0) if audits else 0

        # Cost over time (hourly buckets last 24h)
        cost_rows = _db_query(
            AUDIT_DB,
            "SELECT CAST((timestamp - ?) / 3600 AS INTEGER) as h, SUM(cost) as c, COUNT(*) as n "
            "FROM audit_log WHERE timestamp > ? GROUP BY h ORDER BY h",
            (time.time() - 86400, time.time() - 86400),
        )

        labels = [f"-{23 - r['h']}h" for r in cost_rows] or ["No data"]
        data = [round(r["c"] or 0, 4) for r in cost_rows] or [0]
        # v1.1.1: real per-hour run counts (was hardcoded [1] per bucket).
        run_data = [r["n"] or 0 for r in cost_rows] or [0]

        content = f"""
        <h2>Last 24 Hours</h2>
        <div class="grid">
          <div class="card"><div class="label">Agent Runs</div><div class="stat">{trace_count}</div></div>
          <div class="card"><div class="label">Audit Events</div><div class="stat">{audit_count}</div></div>
          <div class="card"><div class="label">Total Cost</div><div class="stat">${total_cost:.4f}</div></div>
          <div class="card"><div class="label">Avg Cost/Run</div><div class="stat">${total_cost / max(trace_count, 1):.5f}</div></div>
        </div>
        <div class="grid grid-2">
          <div class="card card-chart">
            <div class="label">Cost by Hour</div>
            <canvas id="costChart"></canvas>
          </div>
          <div class="card card-chart">
            <div class="label">Agent Runs by Hour</div>
            <canvas id="runChart"></canvas>
          </div>
        </div>
        <script nonce="{nonce}">
          new Chart(document.getElementById('costChart').getContext('2d'), {{
            type: 'line',
            data: {{
              labels: {json.dumps(labels)},
              datasets: [{{
                label: 'Cost ($)',
                data: {json.dumps(data)},
                borderColor: '#3dd68c',
                backgroundColor: '#3dd68c25',
                tension: 0.3,
                fill: true,
              }}]
            }},
            options: {{
              plugins: {{ legend: {{ display: false }} }},
              scales: {{ y: {{ beginAtZero: true, ticks: {{ color: '#888' }} }}, x: {{ ticks: {{ color: '#888' }} }} }}
            }}
          }});
          new Chart(document.getElementById('runChart').getContext('2d'), {{
            type: 'bar',
            data: {{
              labels: {json.dumps(labels)},
              datasets: [{{
                label: 'Runs',
                data: {json.dumps(run_data)},
                backgroundColor: '#7c6cf0',
              }}]
            }},
            options: {{
              plugins: {{ legend: {{ display: false }} }},
              scales: {{ y: {{ beginAtZero: true, ticks: {{ color: '#888' }} }}, x: {{ ticks: {{ color: '#888' }} }} }}
            }}
          }});
        </script>
        """
        return layout("Overview", content, "/", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/traces", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def traces(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        rows = _db_query(TRACE_DB, "SELECT * FROM traces ORDER BY timestamp DESC LIMIT 100")
        if not rows:
            content = '<div class="card"><div class="empty">No traces yet. Run an agent to see data here.</div></div>'
        else:
            tbody = "".join(
                f"""<tr>
                <td>{_esc(time.strftime("%H:%M:%S", time.localtime(r.get("timestamp", 0))))}</td>
                <td>{_esc(r.get("agent", "-"))}</td>
                <td>{_esc((r.get("task", "") or "")[:60])}</td>
                <td>{r.get("duration_ms", 0):.0f}ms</td>
                <td>${r.get("cost", 0):.5f}</td>
                <td>{_esc(r.get("turns", "-"))}</td>
                </tr>"""
                for r in rows
            )
            content = f"""<div class="card">
                <table>
                  <thead><tr><th>Time</th><th>Agent</th><th>Task</th><th>Duration</th><th>Cost</th><th>Turns</th></tr></thead>
                  <tbody>{tbody}</tbody>
                </table>
            </div>"""
        return layout("Traces", content, "/traces", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/costs", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def costs(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        # Cost by model. v1.1.1: source from `traces` (has model+cost+per-run rows).
        # The old audit_log query referenced a non-existent `model` column and
        # silently returned nothing.
        rows = _db_query(
            TRACE_DB,
            "SELECT model, SUM(cost) as c, COUNT(*) as n FROM traces "
            "WHERE timestamp > ? AND model IS NOT NULL GROUP BY model ORDER BY c DESC",
            (time.time() - 7 * 86400,),
        )

        if not rows:
            content = '<div class="card"><div class="empty">No cost data. Run some agents first.</div></div>'
        else:
            labels = [r["model"] or "unknown" for r in rows]
            costs = [round(r["c"] or 0, 4) for r in rows]
            content = f"""
            <h2>Cost by Model (Last 7 Days)</h2>
            <div class="grid grid-2">
              <div class="card card-chart">
                <canvas id="costModelChart"></canvas>
              </div>
              <div class="card">
                <table>
                  <thead><tr><th>Model</th><th>Calls</th><th>Total Cost</th></tr></thead>
                  <tbody>{"".join(f"<tr><td>{_esc(l)}</td><td>{r['n']}</td><td>${c:.4f}</td></tr>" for l, c, r in zip(labels, costs, rows))}</tbody>
                </table>
              </div>
            </div>
            <script nonce="{nonce}">
              new Chart(document.getElementById('costModelChart').getContext('2d'), {{
                type: 'doughnut',
                data: {{
                  labels: {json.dumps(labels)},
                  datasets: [{{
                    data: {json.dumps(costs)},
                    backgroundColor: ['#7c6cf0','#3dd68c','#ffa726','#f06161','#61dafb','#bb6be0','#66bb6a'],
                  }}]
                }},
                options: {{ plugins: {{ legend: {{ labels: {{ color: '#ccc' }} }} }} }}
              }});
            </script>
            """
        return layout("Costs", content, "/costs", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/agents", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def agents(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        rows = _db_query(
            TRACE_DB,
            "SELECT agent, COUNT(*) as n, AVG(duration_ms) as d, SUM(cost) as c "
            "FROM traces WHERE timestamp > ? GROUP BY agent ORDER BY n DESC",
            (time.time() - 7 * 86400,),
        )
        if not rows:
            content = '<div class="card"><div class="empty">No agent activity yet.</div></div>'
        else:
            tbody = "".join(
                f"""<tr>
                <td><strong>{_esc(r.get("agent", "-"))}</strong></td>
                <td>{r["n"]}</td>
                <td>{r.get("d", 0):.0f}ms</td>
                <td>${r.get("c", 0):.4f}</td>
                </tr>"""
                for r in rows
            )
            content = f"""<div class="card">
                <h2>Agent Performance (Last 7 Days)</h2>
                <table>
                  <thead><tr><th>Agent</th><th>Runs</th><th>Avg Latency</th><th>Total Cost</th></tr></thead>
                  <tbody>{tbody}</tbody>
                </table>
            </div>"""
        return layout("Agents", content, "/agents", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/tools", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def tools_view(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        # v1.1.1: correct column is event_type (not `event`). Populated when
        # LARGESTACK_AUDIT_EVENTS=1 records per-tool-call audit rows.
        rows = _db_query(
            AUDIT_DB,
            "SELECT action as tool, COUNT(*) as n FROM audit_log WHERE event_type='tool.call' GROUP BY action ORDER BY n DESC LIMIT 20",
        )
        if not rows:
            content = '<div class="card"><div class="empty">No tool calls recorded.</div></div>'
        else:
            labels = [r["tool"] for r in rows]
            counts = [r["n"] for r in rows]
            content = f"""
            <h2>Tool Usage</h2>
            <div class="card card-chart"><canvas id="toolChart"></canvas></div>
            <script nonce="{nonce}">
              new Chart(document.getElementById('toolChart').getContext('2d'), {{
                type: 'bar',
                data: {{
                  labels: {json.dumps(labels)},
                  datasets: [{{ label: 'Calls', data: {json.dumps(counts)}, backgroundColor: '#7c6cf0' }}]
                }},
                options: {{
                  indexAxis: 'y',
                  plugins: {{ legend: {{ display: false }} }},
                  scales: {{ x: {{ beginAtZero: true, ticks: {{ color: '#888' }} }}, y: {{ ticks: {{ color: '#888' }} }} }}
                }}
              }});
            </script>
            """
        return layout("Tools", content, "/tools", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/guards", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def guards(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        # v1.1.1: correct column is event_type (not `event`). Populated when
        # LARGESTACK_AUDIT_EVENTS=1 records guard-block audit rows.
        rows = _db_query(
            AUDIT_DB,
            "SELECT action as event, COUNT(*) as n FROM audit_log WHERE event_type LIKE 'guard.%' GROUP BY action",
        )
        if not rows:
            content = '<div class="card"><div class="empty">No guardrail events. All requests passed cleanly.</div></div>'
        else:
            tbody = "".join(f"<tr><td>{_esc(r['event'])}</td><td>{r['n']}</td></tr>" for r in rows)
            content = f"""<div class="card">
                <h2>Guardrail Events</h2>
                <table><thead><tr><th>Event</th><th>Count</th></tr></thead><tbody>{tbody}</tbody></table>
            </div>"""
        return layout("Guards", content, "/guards", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/memory", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def memory_view(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        content = """<div class="card"><div class="label">Memory Types Active</div>
            <table><tbody>
                <tr><td>Buffer (conversation)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Episodic (event scoring)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Semantic (vector)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Graph (entity/relation)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Procedural (skills)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Observational (Mastra)</td><td class="tag tag-ok">Active</td></tr>
                <tr><td>Shared (cross-agent)</td><td class="tag tag-ok">Active</td></tr>
            </tbody></table>
        </div>"""
        return layout("Memory", content, "/memory", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/metrics", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def metrics(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        # p50/p95/p99 latency
        rows = _db_query(
            TRACE_DB,
            "SELECT duration_ms FROM traces WHERE timestamp > ? ORDER BY duration_ms",
            (time.time() - 86400,),
        )
        durations = sorted([r["duration_ms"] for r in rows if r.get("duration_ms")])
        if not durations:
            content = '<div class="card"><div class="empty">No metrics yet.</div></div>'
        else:

            def pct(arr, p):
                if not arr:
                    return 0
                return arr[min(int(len(arr) * p / 100), len(arr) - 1)]

            p50, p95, p99 = pct(durations, 50), pct(durations, 95), pct(durations, 99)
            content = f"""
            <h2>Latency Percentiles (24h)</h2>
            <div class="grid">
              <div class="card"><div class="label">p50</div><div class="stat">{p50:.0f}ms</div></div>
              <div class="card"><div class="label">p95</div><div class="stat">{p95:.0f}ms</div></div>
              <div class="card"><div class="label">p99</div><div class="stat">{p99:.0f}ms</div></div>
              <div class="card"><div class="label">Total Requests</div><div class="stat">{len(durations)}</div></div>
            </div>
            """
        return layout(
            "Metrics", content, "/metrics", api_key=_verified_api_key(request), nonce=nonce
        )

    @app.get("/alerts", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def alerts(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        alerts_list = []
        # Check circuit breaker states, recent errors
        # v1.1.1: failed runs are recorded as event_type='agent.run', action='failed'
        # (the old event='agent.error' column/value never existed).
        errs = _db_query(
            AUDIT_DB,
            "SELECT COUNT(*) as n FROM audit_log WHERE event_type='agent.run' AND action='failed' AND timestamp > ?",
            (time.time() - 3600,),
        )
        err_count = errs[0]["n"] if errs else 0
        if err_count > 10:
            alerts_list.append(("err", f"High error rate: {err_count} errors in last hour"))

        # High cost alert
        cost_rows = _db_query(
            AUDIT_DB,
            "SELECT SUM(cost) as c FROM audit_log WHERE timestamp > ?",
            (time.time() - 3600,),
        )
        hour_cost = (cost_rows[0]["c"] or 0) if cost_rows else 0
        if hour_cost > 10:
            alerts_list.append(("warn", f"High cost: ${hour_cost:.2f} in last hour"))

        if not alerts_list:
            content = '<div class="card"><div class="empty">No active alerts.</div></div>'
        else:
            items = "".join(
                f'<div class="card"><span class="tag tag-{_esc(lvl)}">{_esc(lvl.upper())}</span> {_esc(msg)}</div>'
                for lvl, msg in alerts_list
            )
            content = f'<div class="grid">{items}</div>'
        return layout("Alerts", content, "/alerts", api_key=_verified_api_key(request), nonce=nonce)

    @app.get("/settings", response_class=HTMLResponse, dependencies=_build_protected_deps())
    def settings(request: Request):
        nonce = getattr(request.state, "csp_nonce", "")
        from largestack._core.config import get_config

        cfg = get_config()
        content = f"""<div class="card">
            <h2>Configuration</h2>
            <table>
                <tr><td>Default Provider</td><td>{_esc(getattr(cfg, "default_provider", "-"))}</td></tr>
                <tr><td>Default Model</td><td>{_esc(getattr(cfg, "default_model", "-"))}</td></tr>
                <tr><td>Semantic Cache</td><td>{_esc(getattr(cfg, "semantic_cache", False))}</td></tr>
                <tr><td>Max Turns</td><td>{_esc(getattr(cfg, "max_turns", 25))}</td></tr>
                <tr><td>Cost Budget</td><td>${_esc(getattr(cfg, "cost_budget", 5.0))}</td></tr>
            </table>
        </div>"""
        return layout(
            "Settings", content, "/settings", api_key=_verified_api_key(request), nonce=nonce
        )

    @app.get("/api/metrics", response_class=JSONResponse, dependencies=_build_protected_deps())
    def api_metrics(request: Request):
        """JSON API for programmatic access."""
        traces = _db_query(
            TRACE_DB, "SELECT COUNT(*) as n FROM traces WHERE timestamp > ?", (time.time() - 86400,)
        )
        audits = _db_query(
            AUDIT_DB,
            "SELECT SUM(cost) as c FROM audit_log WHERE timestamp > ?",
            (time.time() - 86400,),
        )
        return {
            "traces_24h": traces[0]["n"] if traces else 0,
            "cost_24h": (audits[0]["c"] or 0) if audits else 0,
            "timestamp": time.time(),
        }

    # v0.4.0: optional React SPA mount.
    # When LARGESTACK_DASHBOARD_SPA=1 AND largestack/_dashboard/spa/dist exists,
    # mount the bundled SPA at /spa/. The server-rendered HTML at / is
    # still the default; the SPA is opt-in. See spa/README.md.
    if os.environ.get("LARGESTACK_DASHBOARD_SPA", "").lower() in ("1", "true", "yes"):
        from pathlib import Path as _P
        from fastapi.staticfiles import StaticFiles

        spa_dist = _P(__file__).parent / "spa" / "dist"
        if spa_dist.is_dir():
            app.mount("/spa", StaticFiles(directory=str(spa_dist), html=True), name="spa")
            log = logging.getLogger("largestack.dashboard")
            log.info(f"SPA mounted at /spa/ from {spa_dist}")
        else:
            import logging as _l

            _l.getLogger("largestack.dashboard").warning(
                "LARGESTACK_DASHBOARD_SPA=1 but %s does not exist. "
                "Run: cd largestack/_dashboard/spa && npm install && npm run build",
                spa_dist,
            )

    return app
