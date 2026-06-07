"""Tests for enhanced dashboard with charts."""

import sys

sys.path.insert(0, ".")


def test_dashboard_creates():
    from largestack._dashboard.app import create_app

    app = create_app()
    assert app is not None


def test_dashboard_has_10_views():
    from largestack._dashboard.app import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    # Should have all 10 views
    expected = [
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
    ]
    for p in expected:
        assert p in paths, f"Missing route: {p}"


def test_dashboard_includes_chartjs(monkeypatch):
    """Dashboard HTML should include Chart.js for real visualizations."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    # Chart.js should be in the response
    assert "chart.js" in r.text.lower() or "chart.umd" in r.text.lower()


def test_dashboard_overview_renders(monkeypatch):
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert "Largestack AI" in r.text


def test_dashboard_api_metrics(monkeypatch):
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/api/metrics", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    data = r.json()
    assert "traces_24h" in data
    assert "cost_24h" in data
    assert "timestamp" in data


def test_dashboard_all_views_respond(monkeypatch):
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    # Disable rate limit — this test hits 10 routes back-to-back which would
    # exceed default burst=10 for the same key
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
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
        r = client.get(path, headers={"X-API-Key": "test-key"})
        assert r.status_code == 200, f"{path} returned {r.status_code}"
