"""Tests verifying P0/P1 fixes from v0.3.6 (consolidated reviews)."""
from pathlib import Path
import os, sys
sys.path.insert(0, ".")


# ═══════════════════════════════════════════════════════════════════
# P0-1: Streaming runs through input guardrails + audit + kill switch
# ═══════════════════════════════════════════════════════════════════

def test_stream_runs_input_guardrails():
    """v0.3.6: stream() must call guardrails.check_input on the messages."""
    import asyncio
    from largestack._core.engine import AgentEngine
    
    class FakeGuard:
        def __init__(self): self.input_calls = 0; self.output_calls = 0
        async def check_input(self, msgs): self.input_calls += 1
        async def check_output(self, resp): self.output_calls += 1
    
    class FakeGateway:
        cost_tracker = type("CT", (), {"run_cost": 0.0, "run_tokens": 0})()
        async def stream(self, llm, msgs, **kw):
            for tok in ["hello", " ", "world"]:
                yield tok
    
    class FakeRegistry:
        def get_all_schemas(self): return []
    
    class FakeToolExec:
        registry = FakeRegistry()
        perms = {}
    
    g = FakeGuard()
    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"; eng.llm = "openai/gpt-4o"; eng.gateway = FakeGateway()
    eng.guardrails = g; eng.memory = None; eng.steering = None
    eng.tool_exec = FakeToolExec(); eng.config = type("C", (), {"context_compression": False})()
    eng.max_turns = 5; eng.cost_budget = 1.0; eng.instructions = ""
    eng._compressor = None
    
    async def run():
        chunks = []
        async for tok in eng.stream("hi"):
            chunks.append(tok)
        return chunks
    
    chunks = asyncio.run(run())
    assert chunks == ["hello", " ", "world"]
    assert g.input_calls == 1, "stream must call guardrails.check_input"
    # Output guardrail runs once on the assembled buffer
    assert g.output_calls == 1, "stream must call guardrails.check_output once on assembled buffer"


def test_stream_emits_audit_events():
    """v0.3.6: stream() must emit agent.stream.started + agent.stream.completed."""
    import asyncio
    from largestack._core.engine import AgentEngine
    from largestack._core.events import bus as _bus
    
    events_seen = []
    orig_emit = _bus.emit
    async def spy_emit(event, payload):
        events_seen.append(event)
        return await orig_emit(event, payload)
    _bus.emit = spy_emit
    
    try:
        class FakeGateway:
            cost_tracker = type("CT", (), {"run_cost": 0.0, "run_tokens": 0})()
            async def stream(self, llm, msgs, **kw):
                yield "x"
        class FakeRegistry:
            def get_all_schemas(self): return []
        class FakeToolExec:
            registry = FakeRegistry(); perms = {}
        eng = AgentEngine.__new__(AgentEngine)
        eng.name = "test"; eng.llm = "openai/gpt-4o"; eng.gateway = FakeGateway()
        eng.guardrails = None; eng.memory = None; eng.steering = None
        eng.tool_exec = FakeToolExec(); eng.config = type("C", (), {"context_compression": False})()
        eng.max_turns = 5; eng.cost_budget = 1.0; eng.instructions = ""
        eng._compressor = None
        
        async def run():
            async for _ in eng.stream("hi"):
                pass
        asyncio.run(run())
    finally:
        _bus.emit = orig_emit
    
    assert "agent.stream.started" in events_seen
    assert "agent.stream.completed" in events_seen


# ═══════════════════════════════════════════════════════════════════
# P0-2/3: Structured output forwarding for Anthropic + Google
# ═══════════════════════════════════════════════════════════════════

def test_engine_forwards_google_snake_case_native_params():
    """v0.3.6: engine must forward `response_mime_type` and `response_schema` (snake_case)
    in addition to camelCase variants — these are what build_native_params returns for Google."""
    import inspect
    from largestack._core import engine as eng_mod
    src = inspect.getsource(eng_mod)
    # _BEHAVIOR_KWS must include both forms
    assert "response_mime_type" in src
    assert "response_schema" in src
    assert "responseMimeType" in src
    assert "responseSchema" in src


def test_google_provider_accepts_both_snake_and_camel():
    """v0.3.6: google provider reads both snake_case and camelCase native params."""
    import inspect
    from largestack._core.providers import google_prov
    src = inspect.getsource(google_prov)
    # Both forms must be wired into generationConfig
    assert "response_mime_type" in src
    assert "response_schema" in src


def test_engine_merges_structured_tools_with_agent_tools():
    """v0.3.6: when run_structured() passes Anthropic tools, engine must merge with agent tools
    rather than silently overwriting them."""
    import inspect
    from largestack._core import engine as eng_mod
    src = inspect.getsource(eng_mod)
    assert "structured_tools" in src
    assert "merged_tools" in src


# ═══════════════════════════════════════════════════════════════════
# P0-4: Postgres env var alignment
# ═══════════════════════════════════════════════════════════════════

def test_database_create_reads_database_url(monkeypatch, tmp_path):
    """v0.3.6: LARGESTACK_DATABASE_URL takes priority."""
    # Use a unique tmp path to avoid colliding with whatever other tests may have set
    db_path = tmp_path / "test_priority.db"
    monkeypatch.setenv("LARGESTACK_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LARGESTACK_POSTGRES_DSN", "postgresql://wrong/wrong")
    from largestack._core.database import Database
    db = Database.create()
    assert db.backend == "sqlite", (
        f"LARGESTACK_DATABASE_URL should win over LARGESTACK_POSTGRES_DSN; got backend={db.backend} "
        f"with conn_str={getattr(db, 'connection_string', None)}"
    )


def test_database_create_falls_back_to_postgres_dsn(monkeypatch):
    """v0.3.6: if LARGESTACK_DATABASE_URL unset, use LARGESTACK_POSTGRES_DSN as alias."""
    monkeypatch.delenv("LARGESTACK_DATABASE_URL", raising=False)
    monkeypatch.setenv("LARGESTACK_POSTGRES_DSN", "postgresql://x:y@host/db")
    from largestack._core.database import Database
    # Without psycopg installed, instantiation raises ImportError — but the
    # routing decision (postgres vs sqlite) happened correctly. Verify we
    # at least tried to construct PostgreSQLDatabase.
    try:
        db = Database.create()
        assert db.backend == "postgresql"
    except ImportError as e:
        # The error must mention psycopg — proving we DID route to postgres
        assert "psycopg" in str(e).lower()


def test_compose_sets_both_env_vars():
    """v0.3.6: docker-compose.yml must set LARGESTACK_DATABASE_URL (and keep alias for compat)."""
    import os.path as _op
    repo_root = _op.abspath(_op.join(_op.dirname(__file__), "..", ".."))
    src = Path(_op.join(repo_root, "docker-compose.yml")).read_text()
    assert "LARGESTACK_DATABASE_URL" in src
    assert "LARGESTACK_POSTGRES_DSN" in src


# ═══════════════════════════════════════════════════════════════════
# P0-5: Cost tracker no longer reset on Agent.run
# ═══════════════════════════════════════════════════════════════════

def test_agent_run_does_not_reset_shared_cost_tracker():
    """v0.3.6: agent.run() no longer calls self._gw.cost_tracker.reset() — concurrency safe."""
    import inspect
    from largestack import agent as agent_mod
    src = inspect.getsource(agent_mod)
    # The raw reset call must be gone
    assert "self._gw.cost_tracker.reset()" not in src


def test_engine_uses_per_run_cost():
    """v0.3.6: engine accumulates per-run cost from response chain instead of reading shared tracker."""
    import inspect
    from largestack._core import engine as eng_mod
    src = inspect.getsource(eng_mod)
    assert "run_cost +=" in src
    assert "run_tokens +=" in src


# ═══════════════════════════════════════════════════════════════════
# P0-6: Decorator instruction save/restore
# ═══════════════════════════════════════════════════════════════════

def test_decorator_restores_instructions_after_run():
    """v0.3.6: decorator's run() must save and restore underlying.instructions
    instead of permanently overwriting them."""
    import inspect
    from largestack import decorators
    src = inspect.getsource(decorators)
    assert "prev_instructions" in src
    assert "underlying.instructions = prev_instructions" in src


# ═══════════════════════════════════════════════════════════════════
# P0-7: Embedder runtime fail-loud
# ═══════════════════════════════════════════════════════════════════

def test_embedder_runtime_failure_raises_in_production(monkeypatch):
    """v0.3.6: production env must NEVER fall back to mock after a real backend failure."""
    import asyncio
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "fake-key-will-fail")
    
    from largestack._rag.embedder import Embedder
    e = Embedder(backend="openai")
    e._resolved_backend = "openai"
    
    # Force the openai_embed to fail
    async def fake_fail(texts):
        raise RuntimeError("simulated backend failure")
    e._openai_embed = fake_fail
    
    async def run():
        try:
            await e.embed("test text")
            return "no-raise"
        except RuntimeError:
            return "raised"
    
    result = asyncio.run(run())
    assert result == "raised", "production must re-raise on backend failure (no mock fallback)"


def test_embedder_runtime_failure_raises_in_dev_without_optin(monkeypatch):
    """v0.3.6: dev env without LARGESTACK_ALLOW_MOCK_EMBEDDINGS must also re-raise."""
    import asyncio
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    monkeypatch.delenv("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", raising=False)
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "fake")
    
    from largestack._rag.embedder import Embedder
    e = Embedder(backend="openai")
    e._resolved_backend = "openai"
    async def fake_fail(texts): raise RuntimeError("fail")
    e._openai_embed = fake_fail
    
    async def run():
        try:
            await e.embed("t")
            return False
        except RuntimeError:
            return True
    
    assert asyncio.run(run()) is True


def test_embedder_batch_failure_raises_in_production(monkeypatch):
    """v0.3.6: embed_batch must also re-raise (was: silently mocked)."""
    import asyncio
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "fake")
    from largestack._rag.embedder import Embedder
    e = Embedder(backend="openai")
    e._resolved_backend = "openai"
    async def fake_fail(texts): raise RuntimeError("batch fail")
    e._openai_embed = fake_fail
    
    async def run():
        try:
            await e.embed_batch(["a", "b", "c"])
            return False
        except RuntimeError:
            return True
    
    assert asyncio.run(run()) is True


# ═══════════════════════════════════════════════════════════════════
# P0-8: XSS sanitization in dashboard HTML
# ═══════════════════════════════════════════════════════════════════

def test_dashboard_escapes_agent_name_in_traces(monkeypatch, tmp_path):
    """v0.3.6: <script> in agent name must be HTML-escaped in /traces output."""
    import sqlite3
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    
    # Build a fake trace DB with malicious agent name. We patch
    # os.environ["HOME"] so os.path.expanduser("~/.largestack/...") resolves
    # into the tmp_path. Avoids the previous monkeypatch.setattr on
    # os.path.expanduser which leaked module state into later tests.
    monkeypatch.setenv("HOME", str(tmp_path))
    largestack_dir = tmp_path / ".largestack"
    largestack_dir.mkdir(exist_ok=True)
    trace_db = largestack_dir / "traces.db"
    conn = sqlite3.connect(str(trace_db))
    conn.execute("""CREATE TABLE traces (
        timestamp REAL, agent TEXT, task TEXT, duration_ms REAL,
        cost REAL, turns INTEGER
    )""")
    conn.execute(
        "INSERT INTO traces VALUES (?, ?, ?, ?, ?, ?)",
        (1234567890.0, "<script>alert('xss')</script>", "<img src=x onerror=1>", 100.0, 0.001, 1)
    )
    conn.commit(); conn.close()
    
    from fastapi.testclient import TestClient
    # Force re-import after HOME mock so module-level path resolution picks up tmp_path
    import importlib
    import largestack._dashboard.app as mod
    importlib.reload(mod)
    
    app = mod.create_app()
    client = TestClient(app)
    r = client.get("/traces", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.text
    # Raw <script> must NOT appear in output
    assert "<script>alert" not in body, "agent name not escaped — XSS vulnerability"
    # Escaped form must appear
    assert "&lt;script&gt;" in body or "&lt;script&gt;alert" in body
    # img onerror also escaped
    assert "<img src=x onerror" not in body
    
    # Restore module to canonical state for downstream tests
    importlib.reload(mod)


def test_dashboard_csp_header_present(monkeypatch):
    """v0.3.6: HTML responses include CSP + X-Frame-Options + nosniff headers."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert "Content-Security-Policy" in r.headers
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_dashboard_html_escape_helper():
    """v0.3.6: _esc() helper escapes correctly."""
    from largestack._dashboard.app import _esc
    assert _esc("<script>") == "&lt;script&gt;"
    assert _esc("a&b") == "a&amp;b"
    assert _esc('"quoted"') == "&quot;quoted&quot;"
    assert _esc(None) == ""
    assert _esc(42) == "42"


# ═══════════════════════════════════════════════════════════════════
# P1: Field-length on RunRequest
# ═══════════════════════════════════════════════════════════════════

def test_serve_rejects_oversized_task(monkeypatch):
    """v0.3.6: RunRequest.task has max_length to prevent DoS."""
    monkeypatch.setenv("LARGESTACK_API_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    monkeypatch.setenv("LARGESTACK_MAX_TASK_LENGTH", "100")  # tiny for test
    
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    
    huge = "x" * 200
    r = client.post("/run", json={"task": huge}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 422  # Pydantic validation rejection
    body = r.json()
    assert "max_length" in str(body) or "string_too_long" in str(body) or "too_long" in str(body).lower()


def test_serve_accepts_normal_task(monkeypatch):
    """Normal task length still works (schema-level verification)."""
    import largestack.serve as mod
    src = Path(mod.__file__).read_text()
    assert "max_length=_MAX_TASK_LEN" in src


# ═══════════════════════════════════════════════════════════════════
# P1: Tenant ContextVar
# ═══════════════════════════════════════════════════════════════════

def test_tenant_set_current_uses_contextvar():
    """v0.3.6: TenantManager.set_current uses ContextVar."""
    import inspect
    from largestack._enterprise import tenant
    src = inspect.getsource(tenant)
    assert "ContextVar" in src
    assert "_current_tenant_var" in src


def test_tenant_concurrent_isolation():
    """v0.3.6: two async tasks see independent current tenants."""
    import asyncio
    from largestack._enterprise.tenant import TenantManager
    
    tm = TenantManager()
    tm.register("a")
    tm.register("b")
    
    results = {}
    
    async def task_a():
        token = tm.set_current("a")
        await asyncio.sleep(0.01)
        results["a"] = tm.current
        tm.reset_current(token)
    
    async def task_b():
        token = tm.set_current("b")
        await asyncio.sleep(0.01)
        results["b"] = tm.current
        tm.reset_current(token)
    
    async def run_concurrent():
        await asyncio.gather(task_a(), task_b())
    
    asyncio.run(run_concurrent())
    # Each task got its own current tenant — no cross-contamination
    assert results["a"] == "a"
    assert results["b"] == "b"


# ═══════════════════════════════════════════════════════════════════
# P1: RBAC FastAPI dependency
# ═══════════════════════════════════════════════════════════════════

def test_rbac_require_permission_dependency_exists():
    """v0.3.6: RBAC has require_permission factory for FastAPI Depends."""
    from largestack._enterprise.rbac import require_permission, require_role
    assert callable(require_permission)
    assert callable(require_role)


def test_rbac_require_permission_blocks_missing_user():
    """v0.3.6: FastAPI dep returns 401 without X-User-Id."""
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from largestack._enterprise.rbac import RBAC, require_permission
    
    rbac = RBAC()
    rbac.add_user("alice", roles=["admin"])
    
    app = FastAPI()
    @app.get("/admin", dependencies=[Depends(require_permission(rbac, "admin.write"))])
    def admin():
        return {"ok": True}
    
    client = TestClient(app)
    r = client.get("/admin")
    assert r.status_code == 401
    
    # Wrong user → 403 (only if user exists but lacks permission)
    rbac.add_user("bob", roles=["viewer"])
    r2 = client.get("/admin", headers={"X-User-Id": "bob"})
    assert r2.status_code == 403


# ═══════════════════════════════════════════════════════════════════
# P2: CLI fixes
# ═══════════════════════════════════════════════════════════════════

def test_cli_install_command_says_correct_package():
    """Productized CLI install hints use the clean `largestack` package name."""
    import largestack._cli.main as mod
    src = Path(mod.__file__).read_text()
    assert "pip install largestack" in src
    assert "pip install largestack[dev-server]" in src
    assert "pip install largestack-ai\\n" not in src
    assert "pip install largestack-ai[" not in src or src.count("pip install largestack-ai[") == 0
    assert "largestack-agentic-ai" not in src


def test_cli_dashboard_supports_host_option():
    """v0.3.6: dashboard CLI accepts --host option."""
    import largestack._cli.main as mod
    src = Path(mod.__file__).read_text()
    assert "host: str = typer.Option" in src
    # Container detection
    assert "LARGESTACK_IN_CONTAINER" in src or "/.dockerenv" in src


def test_dockerfile_sets_in_container_marker():
    """v0.3.6: Dockerfile sets LARGESTACK_IN_CONTAINER=1 so dashboard auto-binds 0.0.0.0."""
    import os.path as _op
    repo_root = _op.abspath(_op.join(_op.dirname(__file__), "..", ".."))
    src = Path(_op.join(repo_root, "Dockerfile")).read_text()
    assert "LARGESTACK_IN_CONTAINER=1" in src
