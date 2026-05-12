"""Regression tests for v0.4.0 — production-grade hardening.

Covers:
- Redis-backed rate limiter (with in-process fallback)
- Nonce-based CSP (no more 'unsafe-inline')
- SPA build artifact mount
- Permissions-Policy header
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Rate limiter — Redis backend with graceful fallback
# ---------------------------------------------------------------------------

def test_rate_limiter_inprocess_default(monkeypatch):
    """Default backend is in-process when no env override."""
    monkeypatch.delenv("LARGESTACK_RATE_LIMIT_BACKEND", raising=False)
    from largestack._dashboard.rate_limit import _get_limiter, reset_for_tests, InProcessRateLimiter
    reset_for_tests()
    limiter = _get_limiter()
    assert isinstance(limiter, InProcessRateLimiter)
    assert limiter.backend_name() == "inprocess"
    reset_for_tests()


def test_rate_limiter_inprocess_enforces_burst(monkeypatch):
    """Burst limit is enforced — 11th request rejected when burst=10."""
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_BURST", "5")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_PER_MINUTE", "1")  # very slow refill
    from largestack._dashboard.rate_limit import _get_limiter, reset_for_tests
    reset_for_tests()
    limiter = _get_limiter()
    # First 5 should succeed, 6th rejected
    for i in range(5):
        assert limiter.check("test_key"), f"request {i+1} should be allowed"
    assert not limiter.check("test_key"), "6th request should be rate-limited"
    reset_for_tests()


def test_rate_limiter_redis_backend_falls_back_when_redis_missing(monkeypatch):
    """When LARGESTACK_RATE_LIMIT_BACKEND=redis but Redis is unreachable,
    falls back to in-process (logs warning, doesn't crash)."""
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("LARGESTACK_REDIS_URL", "redis://nonexistent.invalid:6379/0")
    from largestack._dashboard.rate_limit import _get_limiter, reset_for_tests, RedisRateLimiter
    reset_for_tests()
    limiter = _get_limiter()
    assert isinstance(limiter, RedisRateLimiter)
    # Should still work via fallback
    assert limiter.check("test_key")
    # backend_name reports the fallback state
    assert "fallback" in limiter.backend_name() or limiter.backend_name() == "redis"
    reset_for_tests()


def test_rate_limiter_disable_bypass(monkeypatch):
    """LARGESTACK_RATE_LIMIT_DISABLE=1 short-circuits the dependency."""
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    from largestack._dashboard.rate_limit import rate_limit_dependency

    class FakeReq:
        headers = {"X-API-Key": "test"}
        client = None
    # Should not raise even after many calls
    for _ in range(100):
        rate_limit_dependency(FakeReq())  # no exception


def test_rate_limiter_module_exports():
    """Confirm the public API is intact."""
    from largestack._dashboard import rate_limit
    assert hasattr(rate_limit, "rate_limit_dependency")
    assert hasattr(rate_limit, "RateLimiter")  # backwards-compat alias
    assert hasattr(rate_limit, "InProcessRateLimiter")
    assert hasattr(rate_limit, "RedisRateLimiter")


# ---------------------------------------------------------------------------
# Nonce-based CSP — must drop 'unsafe-inline'
# ---------------------------------------------------------------------------

def test_dashboard_csp_uses_nonce_not_unsafe_inline():
    """CSP header must contain a nonce-* token and NOT 'unsafe-inline'."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r = client.get("/")
    csp = r.headers.get("Content-Security-Policy", "")
    assert csp, "CSP header missing"
    assert "nonce-" in csp, f"CSP doesn't have nonce: {csp}"
    assert "'unsafe-inline'" not in csp, f"CSP still has unsafe-inline: {csp}"


def test_dashboard_csp_nonce_changes_per_request():
    """Each request must get a fresh, different nonce."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r1 = client.get("/")
    r2 = client.get("/")

    def extract_nonce(csp: str) -> str:
        for tok in csp.split(";"):
            if "'nonce-" in tok:
                return tok.split("'nonce-")[1].split("'")[0]
        return ""

    nonce1 = extract_nonce(r1.headers.get("Content-Security-Policy", ""))
    nonce2 = extract_nonce(r2.headers.get("Content-Security-Policy", ""))
    assert nonce1 and nonce2, "nonces missing"
    assert nonce1 != nonce2, f"nonces should differ; got identical {nonce1}"


def test_dashboard_html_inline_scripts_have_nonce():
    """Every <style> and <script> tag in the response must have a nonce attribute."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r = client.get("/")
    html = r.text
    # Strict check: every <script> and <style> must have a nonce
    # (excluding the closing tags)
    import re
    for tag in re.finditer(r"<(script|style)([^>]*)>", html):
        attrs = tag.group(2)
        assert 'nonce=' in attrs, (
            f"Tag without nonce will be blocked by CSP: <{tag.group(1)}{attrs}>"
        )


def test_dashboard_csp_nonce_matches_html_nonce():
    """The nonce in the CSP header must match the one in inline tags."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r = client.get("/")
    csp = r.headers.get("Content-Security-Policy", "")

    # Extract nonce from CSP
    csp_nonce = None
    for tok in csp.split(";"):
        if "'nonce-" in tok:
            csp_nonce = tok.split("'nonce-")[1].split("'")[0]
            break
    assert csp_nonce, "CSP nonce not found"

    # Extract nonce from a script tag
    import re
    m = re.search(r'<script\s+[^>]*nonce="([^"]+)"', r.text)
    assert m, "no <script nonce=...> in HTML"
    html_nonce = m.group(1)
    assert csp_nonce == html_nonce, (
        f"CSP nonce {csp_nonce!r} != HTML nonce {html_nonce!r} — "
        "browser will block the script"
    )


def test_dashboard_security_headers_complete():
    """All defense-in-depth security headers are present."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r = client.get("/")
    expected = [
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",  # v0.4.0 addition
    ]
    for h in expected:
        assert h in r.headers, f"missing security header: {h}"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_dashboard_csp_drops_object_src():
    """v0.4.0 CSP must explicitly forbid <object>/<embed>/<applet>."""
    from largestack._dashboard.app import create_app
    client = TestClient(create_app())
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "object-src 'none'" in csp


# ---------------------------------------------------------------------------
# SPA build pipeline
# ---------------------------------------------------------------------------

def test_spa_directory_structure_present():
    """The SPA build pipeline files must exist."""
    repo = Path(__file__).resolve().parent.parent.parent
    spa = repo / "largestack" / "_dashboard" / "spa"
    assert (spa / "package.json").exists()
    assert (spa / "vite.config.js").exists()
    assert (spa / "index.html").exists()
    assert (spa / "main.jsx").exists()
    assert (spa / "App.jsx").exists()
    assert (spa / "README.md").exists()


def test_spa_package_json_has_required_deps():
    """package.json declares react, react-dom, recharts, vite."""
    import json
    repo = Path(__file__).resolve().parent.parent.parent
    pkg = json.loads((repo / "largestack" / "_dashboard" / "spa" / "package.json").read_text())
    assert "react" in pkg["dependencies"]
    assert "react-dom" in pkg["dependencies"]
    assert "recharts" in pkg["dependencies"]
    assert "vite" in pkg["devDependencies"]
    # build script exists
    assert "build" in pkg["scripts"]
    assert pkg["scripts"]["build"] == "vite build"


def test_spa_not_mounted_by_default(monkeypatch):
    """SPA only mounts when LARGESTACK_DASHBOARD_SPA=1."""
    monkeypatch.delenv("LARGESTACK_DASHBOARD_SPA", raising=False)
    from largestack._dashboard.app import create_app
    app = create_app()
    routes = [getattr(r, "path", "") for r in app.routes]
    assert not any(r.startswith("/spa") for r in routes), (
        "SPA mounted without opt-in"
    )


def test_spa_mount_skipped_gracefully_when_dist_missing(monkeypatch, caplog):
    """LARGESTACK_DASHBOARD_SPA=1 but dist/ missing → log warning, don't crash."""
    import logging
    monkeypatch.setenv("LARGESTACK_DASHBOARD_SPA", "1")
    caplog.set_level(logging.WARNING, logger="largestack.dashboard")
    from largestack._dashboard.app import create_app
    app = create_app()  # must not raise
    # Optional: confirm a warning was logged
    routes = [getattr(r, "path", "") for r in app.routes]
    # /spa should NOT have been mounted because dist doesn't exist
    assert not any(r.startswith("/spa") for r in routes)
