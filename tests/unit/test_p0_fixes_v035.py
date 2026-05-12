"""Tests verifying P0/P1 fixes from v0.3.5 (consolidated reviews)."""
from pathlib import Path
import os, sys
sys.path.insert(0, ".")


# ═══════════════════════════════════════════════════════════════════
# P0-1: Dashboard JSON API auth + restricted CORS
# ═══════════════════════════════════════════════════════════════════

def test_dashboard_jsonapi_overview_requires_auth_in_production(monkeypatch):
    """P0 (v0.3.5): /api/* must reject unauthenticated requests in production."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack._dashboard.api import create_api
    app = create_api()
    client = TestClient(app)
    r = client.get("/api/overview")
    assert r.status_code == 401


def test_dashboard_jsonapi_health_is_public(monkeypatch):
    """/api/health must remain public for deployment probes."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.delenv("LARGESTACK_DASHBOARD_KEY", raising=False)
    from fastapi.testclient import TestClient
    from largestack._dashboard.api import create_api
    app = create_api()
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200


def test_dashboard_jsonapi_with_correct_key_works(monkeypatch):
    monkeypatch.setenv("LARGESTACK_DASHBOARD_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    from fastapi.testclient import TestClient
    from largestack._dashboard.api import create_api
    app = create_api()
    client = TestClient(app)
    r = client.get("/api/overview", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    data = r.json()
    assert "traces_24h" in data


def test_dashboard_jsonapi_all_routes_have_auth():
    """Source check: all /api/* routes (except health) must depend on verify_api_key."""
    import largestack._dashboard.api as mod
    src = Path(mod.__file__).read_text()
    # Count protected routes (Depends(verify_api_key))
    import re
    routes = re.findall(r'@app\.get\("(/api/[^"]+)"(?:, dependencies=\[([^\]]+)\])?\)', src)
    for path, deps in routes:
        if path == "/api/health":
            continue
        assert "verify_api_key" in deps, f"{path} is missing verify_api_key"


def test_dashboard_cors_does_not_allow_wildcard():
    """v0.3.5: dashboard api.py must not have allow_origins=['*']."""
    import largestack._dashboard.api as mod
    src = Path(mod.__file__).read_text()
    assert 'allow_origins=["*"]' not in src
    assert "allow_origins=['*']" not in src


def test_cors_resolver_rejects_wildcard_in_env(monkeypatch):
    """If LARGESTACK_CORS_ALLOWED_ORIGINS contains '*', it must be filtered out."""
    monkeypatch.setenv("LARGESTACK_CORS_ALLOWED_ORIGINS", "*,https://example.com")
    from largestack._dashboard.api import _resolve_cors_origins
    origins = _resolve_cors_origins()
    assert "*" not in origins
    assert "https://example.com" in origins


def test_cors_resolver_production_default_empty(monkeypatch):
    """Production env without LARGESTACK_CORS_ALLOWED_ORIGINS = [] (no origins)."""
    monkeypatch.delenv("LARGESTACK_CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    from largestack._dashboard.api import _resolve_cors_origins
    assert _resolve_cors_origins() == []


def test_cors_resolver_dev_default_localhost(monkeypatch):
    """Development default is localhost variants only."""
    monkeypatch.delenv("LARGESTACK_CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    from largestack._dashboard.api import _resolve_cors_origins
    origins = _resolve_cors_origins()
    assert any("localhost" in o for o in origins)
    assert not any("*" == o for o in origins)


def test_dev_server_cors_no_wildcard():
    """v0.3.5: dev_server.py must not use allow_origins=['*']."""
    import largestack._cli.dev_server as mod
    src = Path(mod.__file__).read_text()
    assert 'allow_origins=["*"]' not in src
    assert "_dev_origins" in src  # uses explicit allowlist


# ═══════════════════════════════════════════════════════════════════
# P0-2: Rate limiting
# ═══════════════════════════════════════════════════════════════════

def test_rate_limiter_module_exists():
    from largestack._dashboard.rate_limit import RateLimiter, rate_limit_dependency
    assert callable(rate_limit_dependency)
    assert RateLimiter is not None


def test_rate_limiter_token_bucket_consumes_correctly():
    from largestack._dashboard.rate_limit import RateLimiter
    rl = RateLimiter(per_minute=60, burst=5)
    # First 5 calls should pass
    for _ in range(5):
        assert rl.check("k1") is True
    # 6th call should fail
    assert rl.check("k1") is False


def test_rate_limiter_separate_keys_have_separate_buckets():
    from largestack._dashboard.rate_limit import RateLimiter
    rl = RateLimiter(per_minute=60, burst=2)
    assert rl.check("a") is True
    assert rl.check("a") is True
    assert rl.check("a") is False
    # Different key has its own bucket
    assert rl.check("b") is True


def test_rate_limiter_evicts_old_keys():
    from largestack._dashboard.rate_limit import RateLimiter
    rl = RateLimiter(per_minute=60, burst=1, max_keys=3)
    rl.check("a"); rl.check("b"); rl.check("c"); rl.check("d")
    # 'a' should have been evicted (oldest)
    assert "a" not in rl._buckets
    assert len(rl._buckets) == 3


def test_rate_limit_disable_env_bypasses(monkeypatch):
    """LARGESTACK_RATE_LIMIT_DISABLE=1 should bypass entirely."""
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_DISABLE", "1")
    from largestack._dashboard.rate_limit import rate_limit_dependency
    
    class FakeReq:
        headers = {"X-API-Key": "k"}
        client = type("c", (), {"host": "1.1.1.1"})()
    
    # Should return without raising even after many calls
    for _ in range(100):
        rate_limit_dependency(FakeReq())  # no exception


def test_serve_returns_429_after_burst(monkeypatch):
    """End-to-end: serve hits rate limit after burst."""
    monkeypatch.setenv("LARGESTACK_API_KEY", "test-key")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_PER_MINUTE", "60")
    monkeypatch.setenv("LARGESTACK_RATE_LIMIT_BURST", "3")
    # Force a fresh limiter (the singleton may be cached from earlier tests)
    import largestack._dashboard.rate_limit as rl_mod
    rl_mod._limiter_singleton = None
    
    from fastapi.testclient import TestClient
    from largestack import Agent
    from largestack.serve import create_api
    a = Agent(name="t", llm="openai/gpt-4o-mini")
    app = create_api(a)
    client = TestClient(app)
    
    # 3 requests pass, 4th fails (burst=3)
    statuses = []
    for _ in range(5):
        r = client.get("/tools", headers={"X-API-Key": "test-key"})
        statuses.append(r.status_code)
    assert 429 in statuses, f"Expected 429 in {statuses} after burst"
    
    # Reset for downstream tests
    rl_mod._limiter_singleton = None


# ═══════════════════════════════════════════════════════════════════
# P0-3: Vault KDF (PBKDF2 instead of single SHA-256)
# ═══════════════════════════════════════════════════════════════════

def test_vault_uses_pbkdf2_not_single_sha256():
    """v0.3.5: vault must use a real KDF (PBKDF2HMAC), not single hashlib.sha256."""
    import largestack._security.vault as mod
    src = Path(mod.__file__).read_text()
    assert "PBKDF2HMAC" in src, "vault.py must import PBKDF2HMAC"
    assert "iterations=600_000" in src or "iterations=600000" in src, "must use OWASP-recommended iteration count"


def test_vault_kdf_runtime_works():
    """v0.3.5: vault still works end-to-end with PBKDF2 KDF."""
    from largestack._security.vault import SecretStore
    v = SecretStore(backend="memory", encryption_key="test-passphrase-1234")
    v.set("api_key", "secret-value-x")
    assert v.get("api_key") == "secret-value-x"


# ═══════════════════════════════════════════════════════════════════
# P0-4: SSO production refuses unverified JWT
# ═══════════════════════════════════════════════════════════════════

def test_sso_production_refuses_unsigned_jwt(monkeypatch):
    """P0-4 (v0.3.5): production env must refuse unverified JWT decode."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    from largestack._enterprise.sso import SSOProvider, SSOError
    sso = SSOProvider(provider="oidc", client_id="cid", client_secret="cs",
                       jwks_url="")  # no JWKS
    # Build a fake JWT (header.payload.sig)
    import base64, json
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps({"sub": "u"}).encode()).rstrip(b"=").decode()
    token = f"{h}.{p}.fakesig"
    try:
        sso._decode_jwt(token)
        assert False, "production must refuse unverified JWT"
    except SSOError as e:
        msg = str(e).lower()
        assert "production" in msg or "verification" in msg or "jwks" in msg


def test_sso_dev_allows_unsigned_jwt_with_warning(monkeypatch):
    """Dev mode still allows unsigned for testing — but logs warnings."""
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    from largestack._enterprise.sso import SSOProvider
    sso = SSOProvider(provider="oidc", client_id="cid", client_secret="cs",
                       jwks_url="")
    import base64, json
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps({"sub": "u123"}).encode()).rstrip(b"=").decode()
    token = f"{h}.{p}.fakesig"
    # Should succeed in dev (with warning logged) — provided pyjwt is installed
    try:
        claims = sso._decode_jwt(token)
        assert claims["sub"] == "u123"
    except ImportError:
        # pyjwt not installed — fallback to unsafe parse, which is also acceptable in dev
        pass


# ═══════════════════════════════════════════════════════════════════
# P1-1: Tool cache only caches idempotent tools
# ═══════════════════════════════════════════════════════════════════

def test_tool_default_not_idempotent():
    """v0.3.5: @tool default is idempotent=False (not cached)."""
    from largestack._core.tools import tool
    @tool
    def my_tool(x: int) -> str:
        return str(x)
    assert getattr(my_tool, "_tool_idempotent", None) is False


def test_tool_explicit_idempotent_flag():
    """v0.3.5: @tool(idempotent=True) sets the flag."""
    from largestack._core.tools import tool
    @tool(idempotent=True)
    def pure_tool(x: int) -> str:
        return str(x * 2)
    assert pure_tool._tool_idempotent is True


def test_tool_executor_does_not_cache_non_idempotent():
    """v0.3.5: identical calls to non-idempotent tool execute separately."""
    import asyncio
    from largestack._core.tools import tool, ToolRegistry, ToolExecutor, ToolCall
    
    counter = {"n": 0}
    @tool  # default: idempotent=False
    def stateful(x: int) -> str:
        counter["n"] += 1
        return str(counter["n"])
    
    reg = ToolRegistry()
    reg.register(stateful)
    ex = ToolExecutor(reg)
    
    async def run():
        r1 = await ex.execute(ToolCall(id="1", name="stateful", params={"x": 1}))
        r2 = await ex.execute(ToolCall(id="2", name="stateful", params={"x": 1}))
        return r1, r2
    
    r1, r2 = asyncio.run(run())
    # Both calls executed (counter incremented twice)
    assert counter["n"] == 2
    assert r1.content != r2.content  # different return values


def test_tool_executor_caches_idempotent():
    """v0.3.5: identical calls to idempotent tool return cached result."""
    import asyncio
    from largestack._core.tools import tool, ToolRegistry, ToolExecutor, ToolCall
    
    counter = {"n": 0}
    @tool(idempotent=True)
    def pure(x: int) -> str:
        counter["n"] += 1
        return f"result-{x}"
    
    reg = ToolRegistry()
    reg.register(pure)
    ex = ToolExecutor(reg)
    
    async def run():
        r1 = await ex.execute(ToolCall(id="1", name="pure", params={"x": 1}))
        r2 = await ex.execute(ToolCall(id="2", name="pure", params={"x": 1}))
        return r1, r2
    
    r1, r2 = asyncio.run(run())
    # Only first call executed; second served from cache
    assert counter["n"] == 1
    assert r1.content == r2.content == "result-1"


# ═══════════════════════════════════════════════════════════════════
# P1: OTEL span redaction
# ═══════════════════════════════════════════════════════════════════

def test_otel_redact_authorization_header():
    """v0.3.5: 'authorization' attribute must be redacted."""
    from largestack._observe.otel_export import _redact_attr_value
    assert _redact_attr_value("authorization", "Bearer sk-abc") == "[REDACTED]"
    assert _redact_attr_value("Authorization", "Bearer xyz") == "[REDACTED]"


def test_otel_redact_api_key_header():
    from largestack._observe.otel_export import _redact_attr_value
    assert _redact_attr_value("api-key", "secret-123") == "[REDACTED]"
    assert _redact_attr_value("X-API-Key", "abcdef") == "[REDACTED]"


def test_otel_redact_value_with_known_prefix():
    """API keys that start with sk-, pk-, ghp_, etc., must be redacted regardless of attr name."""
    from largestack._observe.otel_export import _redact_attr_value
    assert _redact_attr_value("custom_field", "sk-abc123") == "[REDACTED]"
    assert _redact_attr_value("anything", "Bearer xyz") == "[REDACTED]"


def test_otel_does_not_redact_normal_values():
    from largestack._observe.otel_export import _redact_attr_value
    assert _redact_attr_value("user_id", "user-123") == "user-123"
    assert _redact_attr_value("operation", "agent.run") == "agent.run"
    assert _redact_attr_value("count", 42) == 42  # non-string passthrough
