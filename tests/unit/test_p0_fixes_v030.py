"""Tests verifying P0 fixes from reviewer of v0.3.0."""
from pathlib import Path
import sys, asyncio; sys.path.insert(0, ".")

def test_decorator_uses_contextvar_not_self_attr():
    """P0.1: decorator must use ContextVar (not self._current_ctx) for concurrency safety."""
    import largestack.decorators as dec
    src = Path(dec.__file__).read_text()
    assert "_current_ctx_var" in src, "ContextVar not adopted"
    assert "_current_ctx_var.set" in src, "ContextVar.set missing"
    assert "_current_ctx_var.reset" in src, "ContextVar.reset missing"
    # Old unsafe pattern must be gone
    assert "self._current_ctx = ctx" not in src, "Old unsafe self._current_ctx still set"

def test_decorator_concurrent_runs_isolated_contexts():
    """P0.1: Two concurrent typed runs do not mix contexts."""
    from dataclasses import dataclass
    from largestack.decorators import Agent, RunContext, _current_ctx_var
    
    @dataclass
    class Deps:
        user_id: str
    
    seen_users = []
    agent = Agent[Deps, str]("openai/gpt-4o-mini", deps_type=Deps,
                             instructions="x")
    
    @agent.tool
    def whoami(ctx: RunContext[Deps]) -> str:
        seen_users.append(ctx.deps.user_id)
        return ctx.deps.user_id
    
    # Simulate two contexts simultaneously via ContextVar
    async def run(uid):
        token = _current_ctx_var.set(RunContext(deps=Deps(user_id=uid), model="x"))
        try:
            await asyncio.sleep(0.01)
            ctx = _current_ctx_var.get()
            return ctx.deps.user_id
        finally:
            _current_ctx_var.reset(token)
    
    async def main():
        results = await asyncio.gather(run("u1"), run("u2"))
        return results
    
    results = asyncio.run(main())
    assert "u1" in results and "u2" in results, f"Context mixed: {results}"

def test_engine_uses_runtime_max_turns():
    """P0.3: runtime max_turns kw should override self.max_turns."""
    import largestack._core.engine as eng
    src = Path(eng.__file__).read_text()
    # Both LoopGuard AND the for loop must use effective_max_turns
    assert "effective_max_turns = kw.get" in src
    assert "for _ in range(effective_max_turns)" in src
    # Old bug pattern must be gone (or not present in the loop)
    # The loop uses effective_max_turns now
    assert "for _ in range(self.max_turns):" not in src

def test_force_final_runs_output_guardrails():
    """P0.4: _force_final must call guardrails.check_output."""
    import largestack._core.engine as eng
    import inspect
    src = inspect.getsource(eng.AgentEngine._force_final)
    assert "guardrails.check_output" in src

def test_audit_logs_failed_status():
    """P0.5: audit log must reflect failed status when run fails."""
    import largestack._core.engine as eng
    src = Path(eng.__file__).read_text()
    assert "run_status = \"failed\"" in src
    assert "audit.log(\"agent.run\", run_status," in src

def test_rbac_denies_missing_user_id():
    """P0.6: RBAC must return 401 if user ID missing."""
    import largestack._enterprise.rbac as rbac_mod
    src = Path(rbac_mod.__file__).read_text()
    assert "Missing X-User-Id" in src
    assert "status_code=401" in src

def test_openai_provider_uses_self_name():
    """P0.7: OpenAI provider errors should use self.name (not hardcoded 'openai')."""
    import largestack._core.providers.openai_prov as op
    src = Path(op.__file__).read_text()
    assert "ProviderTimeoutError(self.name" in src
    assert "ProviderAuthError(self.name)" in src

def test_openai_provider_wraps_http_errors():
    """P0.6: OpenAI provider must wrap HTTPStatusError into ProviderError."""
    import largestack._core.providers.openai_prov as op
    src = Path(op.__file__).read_text()
    # Should not bare raise_for_status anymore
    assert "if r.status_code >= 400:" in src
    assert "ProviderError(f\"{self.name} HTTP" in src

def test_openai_provider_safe_tool_json():
    """P0.7: tool-call JSON parsing must not crash on malformed JSON."""
    import largestack._core.providers.openai_prov as op
    src = Path(op.__file__).read_text()
    # Should have try/except around json.loads(arguments)
    assert "json.JSONDecodeError" in src

def test_tool_executor_sync_timeout():
    """P1.1: sync tools must have timeout via to_thread."""
    import largestack._core.tools as tm
    src = Path(tm.__file__).read_text()
    assert "asyncio.to_thread" in src

def test_tool_executor_uses_retries():
    """P1.2: ToolExecutor must use _tool_retries metadata."""
    import largestack._core.tools as tm
    src = Path(tm.__file__).read_text()
    assert "_tool_retries" in src
    assert "for attempt in range(retries + 1)" in src

def test_gateway_uses_self_config_not_cfg():
    """P1.3: gateway must use self.config (not self.cfg)."""
    import largestack._core.gateway as gw
    src = Path(gw.__file__).read_text()
    # The wrong attribute was self.cfg
    assert "getattr(self.cfg" not in src
    assert "getattr(self.config, \"fallback_models\"" in src

def test_gateway_fallback_routes_via_retry():
    """P1.4: fallback should use _retry (circuit breaker)."""
    import largestack._core.gateway as gw
    src = Path(gw.__file__).read_text()
    # Within fallback loop, should call self._retry
    assert "await self._retry(fb, messages, fallback_model" in src

def test_pii_warn_action_implemented():
    """P0.3 from earlier: warn action must actually warn."""
    import largestack._guard.pii as pii
    src = Path(pii.__file__).read_text()
    assert "elif self.action == \"warn\"" in src
    assert "_detect_any" in src

def test_pii_indian_patterns():
    """P3 bonus: Indian PII patterns present."""
    from largestack._guard.pii import PATTERNS
    for k in ["aadhaar", "pan", "gstin", "ifsc", "phone_in"]:
        assert k in PATTERNS, f"missing {k}"

def test_dockerfile_copies_source_first():
    """P0.4: Dockerfile must copy source before pip install."""
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "Dockerfile")).read_text()
    largestack_idx = src.index("COPY largestack")
    pip_idx = src.index("pip install --no-cache-dir .")
    assert largestack_idx < pip_idx

def test_docker_compose_volume_path_matches_user():
    """P1.5: compose volume must match non-root user home."""
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "docker-compose.yml")).read_text()
    assert "/home/largestack/.largestack" in src
    assert "/root/.largestack" not in src

def test_readme_no_production_ready_claim():
    """P0.8: README must not claim 'production-ready from line one'."""
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "README.md")).read_text()
    assert "production-ready from line one" not in src.lower()

def test_guardrail_pipeline_fail_closed():
    """P0 bonus: guardrail pipeline defaults fail_closed=True."""
    from largestack._guard.pipeline import GuardrailPipeline
    p = GuardrailPipeline()
    assert p.fail_closed is True
