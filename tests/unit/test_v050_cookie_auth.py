"""v0.5.0: Cookie-based session auth on serve API.

Verifies the /login → use cookie → /logout flow, and that X-API-Key
still works alongside cookies (both auth methods accepted).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """Build a serve API with a fixed API key + clean session store."""
    monkeypatch.setenv("LARGESTACK_API_KEY", "test-key-abc-123")
    monkeypatch.delenv("LARGESTACK_SESSION_BACKEND", raising=False)

    # Reset session store singleton between tests
    from largestack.serve import _get_session_store
    if hasattr(_get_session_store, "_store"):
        delattr(_get_session_store, "_store")

    from largestack import Agent
    from largestack.serve import create_api
    agent = Agent(name="cookietest", llm="openai/gpt-4o-mini")
    yield TestClient(create_api(agent))


def test_login_with_correct_api_key_sets_cookie(client):
    r = client.post("/login", headers={"X-API-Key": "test-key-abc-123"})
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert body["ttl_seconds"] == 3600
    assert "largestack_session" in r.cookies


def test_login_with_wrong_api_key_returns_401(client):
    r = client.post("/login", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_login_without_api_key_returns_401(client):
    r = client.post("/login")
    assert r.status_code == 401


def test_authenticated_request_works_with_cookie(client):
    login = client.post("/login", headers={"X-API-Key": "test-key-abc-123"})
    sid = login.cookies["largestack_session"]
    # Tools is a protected endpoint
    client.cookies.set("largestack_session", sid)
    r = client.get("/tools")
    assert r.status_code == 200


def test_authenticated_request_works_with_x_api_key_header(client):
    """Both auth methods should be accepted simultaneously."""
    r = client.get("/tools", headers={"X-API-Key": "test-key-abc-123"})
    assert r.status_code == 200


def test_request_without_any_auth_returns_401(client):
    r = client.get("/tools")
    assert r.status_code == 401


def test_logout_revokes_cookie(client):
    login = client.post("/login", headers={"X-API-Key": "test-key-abc-123"})
    sid = login.cookies["largestack_session"]

    # Verify cookie works
    client.cookies.set("largestack_session", sid)
    r = client.get("/tools")
    assert r.status_code == 200

    # Logout
    client.cookies.set("largestack_session", sid)
    r = client.post("/logout")
    assert r.status_code == 200

    # Cookie no longer valid
    client.cookies.set("largestack_session", sid)
    r = client.get("/tools")
    assert r.status_code == 401


def test_invalid_cookie_value_returns_401(client):
    client.cookies.set("largestack_session", "not-a-real-session-id")
    r = client.get("/tools")
    assert r.status_code == 401


def test_login_endpoint_returns_503_when_no_api_key_configured(monkeypatch):
    """If server is in dev mode without LARGESTACK_API_KEY, login is unavailable."""
    monkeypatch.delenv("LARGESTACK_API_KEY", raising=False)

    from largestack.serve import _get_session_store
    if hasattr(_get_session_store, "_store"):
        delattr(_get_session_store, "_store")

    from largestack import Agent
    from largestack.serve import create_api
    agent = Agent(name="nokey", llm="openai/gpt-4o-mini")
    client = TestClient(create_api(agent))

    r = client.post("/login")
    assert r.status_code == 503
    assert "LARGESTACK_API_KEY not set" in r.json()["detail"]


def test_cookie_is_httponly_and_samesite_lax(client):
    """Defense-in-depth: cookie should be HttpOnly + SameSite=Lax."""
    r = client.post("/login", headers={"X-API-Key": "test-key-abc-123"})
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie or "SameSite=Lax" in set_cookie
