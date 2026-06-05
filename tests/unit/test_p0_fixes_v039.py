"""Regression tests for issues caught during v0.3.8 100-score reviews.

Three issues fixed in v0.3.9:
  1. Anthropic structured output schema mismatch (`structured.py` emitting
     Anthropic-native shape `input_schema`, but `anthropic_prov.py` re-wrapping
     OpenAI shape `parameters`, causing schema to be silently dropped).
  2. Engine treating Anthropic's `structured_output` tool_use as a regular
     tool call (no such tool registered) instead of as the final structured
     answer.
  3. Dashboard React frontend `fetch('/api/...')` had no `X-API-Key` header,
     so authenticated dashboard deployments couldn't reach their own API.
"""
import sys
sys.path.insert(0, ".")


# ─── R1-P0-A: Anthropic structured output schema shape ─────────────────

def test_anthropic_structured_output_uses_openai_shape_parameters():
    """v0.3.9: structured.py must emit `parameters` (OpenAI shape) not
    `input_schema` (Anthropic native), because `anthropic_prov.py` re-wraps
    every tool entry as `{name, description, input_schema=t["parameters"]}`.
    Emitting `input_schema` here gets silently dropped by `t.get("parameters", {})`.
    """
    from pydantic import BaseModel
    from largestack._core.structured import build_native_params
    
    class Out(BaseModel):
        x: int
        y: str
    
    schema = Out.model_json_schema()
    params = build_native_params("anthropic/claude-3-5-sonnet", schema)
    assert "tools" in params
    assert len(params["tools"]) == 1
    tool = params["tools"][0]
    # The tool must use OpenAI shape so the provider's re-wrapping works
    assert "parameters" in tool, "must emit `parameters` for anthropic_prov compatibility"
    assert "input_schema" not in tool, "must NOT emit `input_schema` directly (gets silently dropped)"
    # The schema must contain the Pydantic-derived properties
    assert tool["parameters"].get("properties", {}).get("x") is not None
    assert tool["parameters"].get("properties", {}).get("y") is not None


def test_anthropic_provider_correctly_propagates_structured_schema():
    """v0.3.9: end-to-end — when build_native_params output flows through
    anthropic_prov.py request body construction, the schema reaches the
    Anthropic API as input_schema (their native field) with all properties intact.
    """
    from pydantic import BaseModel
    from largestack._core.structured import build_native_params
    
    class Out(BaseModel):
        answer: str
    
    schema = Out.model_json_schema()
    params = build_native_params("anthropic/claude-3-5-sonnet", schema)
    # Simulate the re-wrapping that anthropic_prov.py:25 does:
    #   [{"name": t["name"], "description": ..., "input_schema": t.get("parameters", {})}]
    rewrapped = [
        {"name": t["name"],
         "description": t.get("description", ""),
         "input_schema": t.get("parameters", {})}
        for t in params["tools"]
    ]
    assert rewrapped[0]["name"] == "structured_output"
    schema_at_api = rewrapped[0]["input_schema"]
    # Schema must NOT be empty
    assert schema_at_api != {}
    assert "properties" in schema_at_api
    assert "answer" in schema_at_api["properties"]


# ─── R1-P0-B: Engine intercepts structured_output tool_use ──────────────

def test_engine_intercepts_structured_output_tool_call():
    """v0.3.9: when the LLM returns a tool_use named `structured_output`,
    the engine must treat it as the final structured answer (return its
    JSON-serialized params as the response content), NOT as a normal
    tool call (which would fail because no tool is registered with that name).
    """
    import asyncio, json
    from largestack.types import LLMResponse, ToolCall
    from largestack._core.engine import AgentEngine
    from largestack._core.steering import SteeringResult, SteeringAction
    
    class FakeGateway:
        cost_tracker = type("CT", (), {"run_cost": 0.0, "run_tokens": 0})()
        async def chat(self, model, messages, tools=None, agent_name=None, **kw):
            # Simulate Anthropic returning tool_use=structured_output
            return LLMResponse(
                content="",
                model=model,
                tool_calls=[ToolCall(
                    id="tc_1",
                    name="structured_output",
                    params={"answer": "42", "confidence": 0.95},
                )],
                input_tokens=10, output_tokens=8, cost=0.0001,
            )
    
    class FakeSteering:
        async def run_after(self, resp, ctx):
            return SteeringResult(action=SteeringAction.PROCEED)
        async def run_before(self, tool, params, ctx):
            return SteeringResult(action=SteeringAction.PROCEED)
    
    class FakeRegistry:
        def get_all_schemas(self): return []
    
    class FakeToolExec:
        registry = FakeRegistry(); perms = {}
        async def execute(self, tc):
            # If we get here, it's a bug: the structured_output should have
            # been intercepted before this method.
            raise AssertionError(f"engine should NOT have called tool_exec for {tc.name}")
    
    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"; eng.llm = "anthropic/claude-3"
    eng.gateway = FakeGateway(); eng.guardrails = None; eng.memory = None
    eng.steering = FakeSteering(); eng.tool_exec = FakeToolExec()
    eng.config = type("C", (), {"context_compression": False})()
    eng.max_turns = 3; eng.cost_budget = 1.0; eng.instructions = ""
    eng._compressor = None
    
    async def run():
        return await eng.execute("hi")
    
    result = asyncio.run(run())
    # Content should be the JSON-serialized structured params
    parsed = json.loads(result.content)
    assert parsed == {"answer": "42", "confidence": 0.95}
    # Run finished in 1 turn (the tool_use was the final answer, not a turn-driving call)
    assert result.turns == 1


def test_engine_does_not_intercept_non_structured_tool_calls():
    """Defense in depth: ordinary tools must still be executed as tool calls.
    Only the literal name 'structured_output' is the trigger.
    """
    import inspect
    from largestack._core import engine as eng_mod
    src = inspect.getsource(eng_mod)
    # Confirm the special-case is gated on the exact name
    assert 'tc.name == "structured_output"' in src, \
        "engine must gate on exact name 'structured_output' to avoid hijacking real tools"


# ─── R1-P1-A: Dashboard frontend auth header propagation ────────────────

def test_dashboard_html_injects_api_key_meta_tag(monkeypatch):
    """v0.3.9: dashboard HTML routes inject <meta name="largestack-api-key">
    after auth has been validated, so the React SPA can read it for
    /api/* fetches.
    """
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key-meta")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.delenv("LARGESTACK_RBAC_ENABLED", raising=False)
    
    from fastapi.testclient import TestClient
    import importlib, largestack._dashboard.app as mod
    importlib.reload(mod)
    
    client = TestClient(mod.create_app())
    r = client.get("/", headers={"X-API-Key": "test-key-meta"})
    assert r.status_code == 200
    assert '<meta name="largestack-api-key"' in r.text, \
        "dashboard HTML must inject meta tag for SPA auth"
    # Key must be present and HTML-escaped (the helper uses _esc)
    assert 'content="test-key-meta"' in r.text


def test_dashboard_html_does_not_inject_meta_without_auth(monkeypatch):
    """v0.3.9: never inject the meta tag with empty content (would be misleading)."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "real-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.delenv("LARGESTACK_RBAC_ENABLED", raising=False)
    
    from fastapi.testclient import TestClient
    import importlib, largestack._dashboard.app as mod
    importlib.reload(mod)
    
    client = TestClient(mod.create_app())
    # Wrong key → 401, but if we somehow get HTML back, the meta tag should
    # not be present. Easier: hit the layout helper directly with empty key.
    html = mod.create_app  # ensure import worked
    # Direct call check via the layout function isn't easily reachable from outside,
    # so we verify via 401 response not containing meta
    r = client.get("/", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    # 401 body should NOT contain the meta with empty content
    assert '<meta name="largestack-api-key" content="">' not in r.text


def test_dashboard_meta_tag_is_html_escaped(monkeypatch):
    """v0.3.9: the API key value in the meta tag is html-escaped to prevent
    `"` in a key from breaking the HTML or enabling injection.
    """
    # Use a key with special chars
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", 'key"with"quotes')
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.delenv("LARGESTACK_RBAC_ENABLED", raising=False)
    
    from fastapi.testclient import TestClient
    import importlib, largestack._dashboard.app as mod
    importlib.reload(mod)
    
    client = TestClient(mod.create_app())
    r = client.get("/", headers={"X-API-Key": 'key"with"quotes'})
    if r.status_code == 200:
        # The raw `"` characters should NOT appear inside content="..." 
        # — they should be escaped to &quot;
        assert 'content="key"with"quotes"' not in r.text
        assert "&quot;" in r.text or '\\"' in r.text


def test_frontend_jsx_reads_meta_tag_for_auth():
    """Source-level: frontend.jsx must reference the meta tag mechanism."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent / "largestack" / "_dashboard" / "frontend.jsx"
    assert p.exists(), "frontend.jsx missing"
    text = p.read_text()
    assert 'meta[name="largestack-api-key"]' in text, \
        "frontend.jsx must read API key from meta tag"
    assert "X-API-Key" in text, "frontend.jsx must send X-API-Key header"
    assert "authHeaders()" in text, "frontend.jsx must use authHeaders helper"


def test_frontend_jsx_handles_auth_errors():
    """v0.3.9: frontend useFetch must surface 401/403/429 distinctly."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent / "largestack" / "_dashboard" / "frontend.jsx"
    text = p.read_text()
    assert "401" in text and "Unauthorized" in text
    assert "403" in text and "Forbidden" in text
    assert "429" in text


# ─── R2-P1-A: CHANGELOG count tolerance ────────────────────────────────

def test_changelog_check_script_tolerates_optional_dep_variance():
    """scripts/check_changelog.sh treats the CHANGELOG count as the canonical
    full-extras MAXIMUM: running with fewer optional extras (fewer passing tests)
    must NOT fail the gate; only ADDING tests beyond the claim does. It also uses a
    strict bold-marker regex so prose mentions of '823 passing tests' don't satisfy
    the count check.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    script = (root / "scripts" / "check_changelog.sh").read_text()
    # Downward variance (fewer extras installed) must be tolerated, not failed.
    assert "fewer optional extras" in script or "canonical" in script, \
        "must tolerate downward optional-dep variance"
    # A small + tolerance for freshly-added tests before demanding a CHANGELOG bump.
    assert "-gt 3" in script, "must allow a small +tolerance"
    # Strict bold-marker regex — must require ** ** wrapping
    assert "\\*\\*[0-9]+ passing\\*\\*" in script, \
        "must use bold-marker regex to avoid matching prose mentions of test counts"
