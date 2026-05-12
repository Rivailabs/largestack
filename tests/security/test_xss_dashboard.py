"""Security regression — XSS / injection / unsafe-rendering tests.

Each test injects a known XSS payload into a DB row that the dashboard
will render, then confirms the payload appears in escaped form (not raw).
"""
import os
import sqlite3
import importlib

import pytest


XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror='alert(1)'>",
    "javascript:alert('xss')",
    '"><script>alert(/xss/)</script>',
    "<svg onload=alert(1)>",
    "<iframe src='javascript:alert(1)'></iframe>",
    "<a href='javascript:alert(1)'>x</a>",
    "<body onload=alert(1)>",
    "<details open ontoggle=alert(1)>",
    "<input onfocus=alert(1) autofocus>",
]


@pytest.fixture
def auth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.delenv("LARGESTACK_RBAC_ENABLED", raising=False)
    return tmp_path


def _seed_trace(tmp_path, agent: str, task: str = "task"):
    """Insert a single trace row into the dashboard's expected SQLite path."""
    largestack_dir = tmp_path / ".largestack"
    largestack_dir.mkdir(exist_ok=True)
    db = largestack_dir / "traces.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS traces ("
        "timestamp REAL, agent TEXT, task TEXT, duration_ms REAL, cost REAL, turns INTEGER)"
    )
    conn.execute(
        "INSERT INTO traces VALUES (?, ?, ?, ?, ?, ?)",
        (1234567890.0, agent, task, 100.0, 0.001, 1),
    )
    conn.commit()
    conn.close()


def _client(monkeypatch_path_change=False):
    """Reload dashboard so SQLite paths re-read HOME if monkeypatched."""
    import largestack._dashboard.app as mod
    if monkeypatch_path_change:
        importlib.reload(mod)
    from fastapi.testclient import TestClient
    return TestClient(mod.create_app()), mod


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_in_agent_name_is_escaped(auth_env, payload):
    """Every XSS payload in agent name must render escaped, not raw."""
    _seed_trace(auth_env, agent=payload)
    client, _ = _client(monkeypatch_path_change=True)
    r = client.get("/traces", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.text
    # Raw payload must NOT appear
    assert payload not in body, f"unescaped XSS payload rendered: {payload!r}"
    # The opening <script> / <img / etc. must be escaped to &lt;
    if payload.startswith("<"):
        first_tag = payload.split(">")[0] + ">"
        assert first_tag not in body, f"raw HTML tag rendered: {first_tag}"


def test_xss_in_task_field_is_escaped(auth_env):
    payload = "<script>alert('task-xss')</script>"
    _seed_trace(auth_env, agent="ok", task=payload)
    client, _ = _client(monkeypatch_path_change=True)
    r = client.get("/traces", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert payload not in r.text


def test_csp_header_is_strict(auth_env):
    client, _ = _client(monkeypatch_path_change=True)
    r = client.get("/", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    # Required directives
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    # Other security headers
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "strict-origin" in r.headers.get("Referrer-Policy", "")


def test_no_inline_event_handler_in_html(auth_env):
    """Dashboard HTML output must not contain on* event-handler attributes
    on user-controlled data (defense in depth alongside CSP).
    
    The check: the user payload `<div onclick=alert(1)>` must be escaped to
    `&lt;div onclick=alert(1)&gt;`. The escaped form is harmless because it
    renders as inert text — the browser does NOT parse it as an HTML element.
    """
    payload = "<div onclick=alert(1)>x</div>"
    _seed_trace(auth_env, agent=payload)
    client, _ = _client(monkeypatch_path_change=True)
    r = client.get("/traces", headers={"X-API-Key": "test-key"})
    body = r.text
    # The dangerous form (raw `<div onclick=`) must not appear — it would be
    # parsed by the browser as a real HTML element with an event handler.
    assert "<div onclick" not in body, "raw HTML event-handler attribute rendered (XSS)"
    # The escaped form should appear (defense in depth: the text is visible
    # but inert because the angle brackets are entities)
    assert "&lt;div onclick" in body, "payload should be HTML-escaped, not stripped"
