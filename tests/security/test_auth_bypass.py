"""Security regression — auth bypass attempts on dashboard + serve."""

from pathlib import Path
import pytest


# ─── Dashboard ──────────────────────────────────────────────────


def _dashboard_client(monkeypatch, key=None, env="production", rbac=False):
    monkeypatch.setenv("LARGESTACK_ENV", env)
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    if key:
        monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", key)
    else:
        monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    if rbac:
        monkeypatch.setenv("LARGESTACK_RBAC_ENABLED", "1")
    else:
        monkeypatch.delenv("LARGESTACK_RBAC_ENABLED", raising=False)
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    return TestClient(create_app())


def test_dashboard_no_key_in_production_denies_all_routes(monkeypatch):
    client = _dashboard_client(monkeypatch, key=None, env="production")
    for path in [
        "/",
        "/traces",
        "/costs",
        "/agents",
        "/tools",
        "/guards",
        "/memory",
        "/metrics",
        "/alerts",
        "/settings",
    ]:
        r = client.get(path)
        assert r.status_code == 401, f"{path} must require auth in prod, got {r.status_code}"


def test_dashboard_health_remains_public(monkeypatch):
    client = _dashboard_client(monkeypatch, key=None, env="production")
    r = client.get("/health")
    assert r.status_code == 200, "deployment healthcheck must remain public"


def test_dashboard_wrong_key_returns_401(monkeypatch):
    client = _dashboard_client(monkeypatch, key="real-key")
    r = client.get("/", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_dashboard_empty_key_header_returns_401(monkeypatch):
    client = _dashboard_client(monkeypatch, key="real-key")
    r = client.get("/", headers={"X-API-Key": ""})
    assert r.status_code == 401


def test_dashboard_lowercase_key_header_treated_same(monkeypatch):
    """HTTP headers are case-insensitive; FastAPI normalizes."""
    client = _dashboard_client(monkeypatch, key="real-key")
    r = client.get("/", headers={"x-api-key": "real-key"})
    assert r.status_code == 200


def test_dashboard_constant_time_compare_used(monkeypatch):
    """Source must use secrets.compare_digest, not == (timing attacks)."""
    import largestack._dashboard.auth as mod

    src = Path(mod.__file__).read_text()
    assert "secrets.compare_digest" in src
    # No naive == comparison of provided vs expected
    assert "provided == expected" not in src


def test_dashboard_with_rbac_blocks_missing_user(monkeypatch):
    """When RBAC enabled, X-User-Id is required."""
    monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "k")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.setenv("LARGESTACK_RBAC_ENABLED", "1")
    monkeypatch.delenv("LARGESTACK_ENV", raising=False)

    # Reset default RBAC for clean state
    import largestack._enterprise.rbac as rbac_mod

    rbac_mod._default_rbac = None

    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    client = TestClient(create_app())

    # API key valid, but no X-User-Id → 401 from RBAC dep
    r = client.get("/", headers={"X-API-Key": "k"})
    assert r.status_code == 401

    # Cleanup
    rbac_mod._default_rbac = None


def test_dashboard_with_rbac_allows_correct_user(monkeypatch):
    """RBAC allows users with the required permission."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "k")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.setenv("LARGESTACK_RBAC_ENABLED", "1")
    monkeypatch.delenv("LARGESTACK_ENV", raising=False)

    import largestack._enterprise.rbac as rbac_mod

    rbac_mod._default_rbac = None
    rbac = rbac_mod.get_default_rbac()
    rbac.add_user("alice", roles=["viewer"])  # has agent.read

    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    client = TestClient(create_app())

    r = client.get("/", headers={"X-API-Key": "k", "X-User-Id": "alice"})
    assert r.status_code == 200

    rbac_mod._default_rbac = None


# ─── Serve ──────────────────────────────────────────────────────


def _serve_client(monkeypatch, key=None, env="production"):
    monkeypatch.setenv("LARGESTACK_ENV", env)
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    if key:
        monkeypatch.setenv("LARGESTACK_API_KEY", key)
    else:
        monkeypatch.delenv("LARGESTACK_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api

    a = Agent(name="t", llm="openai/gpt-4o-mini")
    return TestClient(create_api(a))


def test_serve_no_key_in_production_denies_run(monkeypatch):
    client = _serve_client(monkeypatch, key=None, env="production")
    r = client.post("/run", json={"task": "hi"})
    assert r.status_code == 401


def test_serve_no_key_in_production_denies_stream(monkeypatch):
    client = _serve_client(monkeypatch, key=None, env="production")
    r = client.post("/stream", json={"task": "hi"})
    assert r.status_code == 401


def test_serve_no_key_in_production_denies_tools(monkeypatch):
    client = _serve_client(monkeypatch, key=None, env="production")
    r = client.get("/tools")
    assert r.status_code == 401


def test_serve_health_probes_remain_public(monkeypatch):
    client = _serve_client(monkeypatch, key=None, env="production")
    for path in ["/health", "/livez", "/readyz"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} must be public, got {r.status_code}"
