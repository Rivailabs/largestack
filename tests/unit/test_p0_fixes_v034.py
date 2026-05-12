"""Tests verifying P0 fixes from v0.3.4 reviewer (Sachith review)."""
from pathlib import Path
import sys, os
sys.path.insert(0, ".")


# ═══════════════════════════════════════════════════════════════════
# B-01: Dashboard auth
# ═══════════════════════════════════════════════════════════════════

def test_dashboard_unauthenticated_request_returns_401_in_production(monkeypatch):
    """B-01 (v0.3.4): without LARGESTACK_DASHBOARD_KEY in production, all routes 401."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 401
    assert "LARGESTACK_DASHBOARD_KEY" in r.text


def test_dashboard_health_is_public(monkeypatch):
    """B-01 (v0.3.4): /health is always public (deployment healthcheck)."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    from largestack import __version__
    assert body["version"] == __version__
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body


def test_dashboard_wrong_key_returns_401(monkeypatch):
    """B-01: wrong X-API-Key returns 401."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "correct-key")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_dashboard_correct_key_works(monkeypatch):
    """B-01: correct X-API-Key returns 200."""
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "correct-key")
    from fastapi.testclient import TestClient
    from largestack._dashboard.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/", headers={"X-API-Key": "correct-key"})
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# B-02: Serve auth
# ═══════════════════════════════════════════════════════════════════

def test_serve_unauthenticated_in_production_returns_401(monkeypatch):
    """B-02 (v0.3.4): without LARGESTACK_API_KEY in production, /run returns 401."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    r = client.post("/run", json={"task": "hi"})
    assert r.status_code == 401
    assert "LARGESTACK_API_KEY" in r.text


def test_serve_health_is_public(monkeypatch):
    """B-02: /health, /livez, /readyz are public."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    for path in ["/health", "/livez", "/readyz"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} should be public, got {r.status_code}"


def test_serve_wrong_key_returns_401(monkeypatch):
    """B-02: wrong X-API-Key returns 401."""
    monkeypatch.setenv("LARGESTACK_API_KEY", "correct-key")
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    r = client.get("/tools", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_serve_correct_key_works(monkeypatch):
    """B-02: correct X-API-Key returns 200."""
    monkeypatch.setenv("LARGESTACK_API_KEY", "correct-key")
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    r = client.get("/tools", headers={"X-API-Key": "correct-key"})
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# B-03: RAG embedder fail-loud
# ═══════════════════════════════════════════════════════════════════

def test_embedder_production_rejects_mock_even_with_optin(monkeypatch):
    """B-03 (v0.3.4): production env always rejects mock embeddings, even with opt-in flag."""
    from largestack._rag.embedder import Embedder
    for k in ("LARGESTACK_OPENAI_API_KEY", "OPENAI_API_KEY", "LARGESTACK_VOYAGE_API_KEY",
              "VOYAGE_API_KEY", "LARGESTACK_COHERE_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.setenv("LARGESTACK_ALLOW_MOCK_EMBEDDINGS", "1")
    
    # Force sentence-transformers import to fail
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *args, **kw):
        if name == "sentence_transformers":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    
    e = Embedder(backend="auto")
    try:
        e._resolve_backend()
        assert False, "production must reject mock embeddings"
    except ImportError as exc:
        assert "production" in str(exc).lower()


def test_embedder_dev_requires_explicit_optin(monkeypatch):
    """B-03 (v0.3.4): development without opt-in flag also rejects mock."""
    from largestack._rag.embedder import Embedder
    for k in ("LARGESTACK_OPENAI_API_KEY", "OPENAI_API_KEY", "LARGESTACK_VOYAGE_API_KEY",
              "VOYAGE_API_KEY", "LARGESTACK_COHERE_API_KEY", "COHERE_API_KEY",
              "LARGESTACK_ALLOW_MOCK_EMBEDDINGS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *args, **kw):
        if name == "sentence_transformers":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    
    e = Embedder(backend="auto")
    try:
        e._resolve_backend()
        assert False, "should require explicit opt-in"
    except ImportError as exc:
        msg = str(exc)
        # Must mention either the env var or the install instruction
        assert "LARGESTACK_ALLOW_MOCK_EMBEDDINGS" in msg or "sentence-transformers" in msg


# ═══════════════════════════════════════════════════════════════════
# B-04: mTLS fail-loud
# ═══════════════════════════════════════════════════════════════════

def test_mtls_module_has_env_gated_stub(monkeypatch):
    """B-04 (v0.3.4): mTLS source must check LARGESTACK_ALLOW_INSECURE_MTLS."""
    import largestack._security.mtls as mtls
    src = Path(mtls.__file__).read_text()
    assert "LARGESTACK_ALLOW_INSECURE_MTLS" in src
    assert "LARGESTACK_ENV" in src
    # Old "fall through silently" pattern must be gone
    assert "log.warning(\"cryptography not installed — using stub CA\")" not in src


# ═══════════════════════════════════════════════════════════════════
# B-10: Tool idempotency LRU + TTL
# ═══════════════════════════════════════════════════════════════════

def test_tool_idem_cache_is_bounded():
    """B-10 (v0.3.4): tool idempotency cache has _IDEM_MAX_SIZE bound."""
    from largestack._core.tools import ToolExecutor, ToolRegistry
    e = ToolExecutor(ToolRegistry())
    assert hasattr(e, "_IDEM_MAX_SIZE")
    assert e._IDEM_MAX_SIZE > 0
    assert hasattr(e, "_IDEM_TTL_SECONDS")


def test_tool_idem_cache_evicts_lru():
    """B-10 (v0.3.4): when capacity exceeded, oldest entries are evicted."""
    from largestack._core.tools import ToolExecutor, ToolRegistry
    e = ToolExecutor(ToolRegistry())
    e._IDEM_MAX_SIZE = 3  # small for test
    e._idem_put("a", "1")
    e._idem_put("b", "2")
    e._idem_put("c", "3")
    e._idem_put("d", "4")  # should evict "a"
    assert len(e._idem) == 3
    assert "a" not in e._idem
    assert "d" in e._idem


def test_tool_idem_cache_ttl_expires():
    """B-10 (v0.3.4): entries past TTL return None on get."""
    from largestack._core.tools import ToolExecutor, ToolRegistry
    e = ToolExecutor(ToolRegistry())
    e._IDEM_TTL_SECONDS = 0  # everything expires immediately
    e._idem_put("k", "v")
    assert e._idem_get("k") is None  # expired


def test_tool_idem_cache_lru_promotion():
    """B-10 (v0.3.4): get() should promote entry to most-recently-used."""
    from largestack._core.tools import ToolExecutor, ToolRegistry
    e = ToolExecutor(ToolRegistry())
    e._IDEM_MAX_SIZE = 3
    e._idem_put("a", "1")
    e._idem_put("b", "2")
    e._idem_put("c", "3")
    # Access "a" — should make it MRU
    e._idem_get("a")
    # Add "d" — should now evict "b" (LRU), not "a"
    e._idem_put("d", "4")
    assert "a" in e._idem
    assert "b" not in e._idem


# ═══════════════════════════════════════════════════════════════════
# RISK-006: Bedrock empty default region
# ═══════════════════════════════════════════════════════════════════

def test_bedrock_region_default_empty():
    """RISK-006 (v0.3.4): bedrock_region default must be empty (opt-in via env)."""
    import largestack._core.config as cfg
    src = Path(cfg.__file__).read_text()
    assert 'bedrock_region: str = ""' in src
    # Old default must be gone
    assert 'bedrock_region: str = "us-east-1"' not in src


def test_gateway_skips_bedrock_when_region_empty(monkeypatch):
    """RISK-006: gateway must NOT instantiate BedrockProvider when region is empty."""
    # Clear any pre-existing region env
    monkeypatch.delenv("LARGESTACK_BEDROCK_REGION", raising=False)
    from largestack._core.gateway import LLMGateway
    from largestack._core.config import LargestackConfig
    cfg = LargestackConfig(bedrock_region="")
    gw = LLMGateway(cfg)
    assert "bedrock" not in gw.providers


def test_gateway_includes_bedrock_when_region_set(monkeypatch):
    """RISK-006: gateway adds bedrock when region is explicitly set."""
    from largestack._core.gateway import LLMGateway
    from largestack._core.config import LargestackConfig
    cfg = LargestackConfig(bedrock_region="us-east-1")
    gw = LLMGateway(cfg)
    # Provider added (whether boto3 is installed or not is separate)
    assert "bedrock" in gw.providers


# ═══════════════════════════════════════════════════════════════════
# B-22: Production compose strict secrets
# ═══════════════════════════════════════════════════════════════════

def test_production_compose_requires_postgres_password():
    """B-22 (v0.3.4): docker-compose.prod.yml must use ${VAR:?error} for required secrets."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(root, "docker-compose.prod.yml")
    assert os.path.exists(path), "docker-compose.prod.yml must exist"
    src = Path(path).read_text()
    # Must require POSTGRES_PASSWORD with no fallback
    assert "${POSTGRES_PASSWORD:?" in src
    # Must require dashboard + API keys
    assert "${LARGESTACK_DASHBOARD_KEY:?" in src
    assert "${LARGESTACK_API_KEY:?" in src


def test_production_compose_real_healthcheck():
    """B-18 (v0.3.4): production compose uses HTTP healthcheck, not just import."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "docker-compose.prod.yml")).read_text()
    assert "curl" in src
    assert "/health" in src


# ═══════════════════════════════════════════════════════════════════
# Auth file structure
# ═══════════════════════════════════════════════════════════════════

def test_dashboard_auth_module_exists():
    """B-01: largestack/_dashboard/auth.py module exists with verify_api_key."""
    from largestack._dashboard.auth import verify_api_key, get_dashboard_api_key, is_production
    assert callable(verify_api_key)
    assert callable(get_dashboard_api_key)
    assert callable(is_production)


def test_dashboard_auth_uses_constant_time_compare():
    """B-01: auth must use secrets.compare_digest, not == (timing attack)."""
    import largestack._dashboard.auth as mod
    src = Path(mod.__file__).read_text()
    assert "secrets.compare_digest" in src
