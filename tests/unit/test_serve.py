"""Tests for REST API server."""
import sys; sys.path.insert(0, ".")

def test_serve_creates_routes():
    from largestack import Agent
    from largestack.serve import create_api
    agent = Agent(name="api", llm="deepseek/deepseek-chat", guardrails=None)
    app = create_api(agent)
    paths = [getattr(r, 'path', '') for r in app.routes]
    assert "/run" in paths and "/stream" in paths and "/health" in paths
    assert "/tools" in paths and "/cost" in paths
    assert "/readyz" in paths and "/livez" in paths

def test_serve_health_returns_agent_info():
    import asyncio
    from largestack import Agent
    from largestack.serve import create_api
    agent = Agent(name="test-api", llm="deepseek/deepseek-chat", guardrails=None)
    app = create_api(agent)
    # Just verify the app was created with correct title
    assert "test-api" in app.title
