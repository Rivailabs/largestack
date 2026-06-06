"""Regression tests for the v1.1.1 review remediation (REVIEW_2026-06-06.md).

Each test pins a specific bug fix so it can't silently regress. All are fast and
offline (no real LLM, no model downloads).
"""
from __future__ import annotations
import asyncio
import os
import sqlite3
import tempfile

import pytest


# ---- F-LLM-1: litellm error mapping must not crash with TypeError ----
def test_litellm_map_exception_no_typeerror():
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    from largestack.errors import ProviderAuthError, ProviderRateLimitError, ProviderError
    p = LiteLLMProvider()
    assert isinstance(p._map_exception(Exception("invalid api key 401")), ProviderAuthError)
    assert isinstance(p._map_exception(Exception("rate limit 429")), ProviderRateLimitError)
    err = p._map_exception(Exception("kaboom"))
    assert isinstance(err, ProviderError) and "kaboom" in str(err)


# ---- F-ENG-3: tool args coerced to annotated scalar types ----
def test_tool_arg_coercion_str_to_int():
    from largestack._core.tools import ToolRegistry, ToolExecutor
    from largestack.types import ToolCall
    def add(a: int, b: int) -> int:
        "add"
        return a + b
    reg = ToolRegistry(); reg.register(add)
    ex = ToolExecutor(reg)
    r = asyncio.run(ex.execute(ToolCall(id="1", name="add", params={"a": "19", "b": "23"})))
    assert r.content == "42"  # not "1923"


# ---- F-ENG-4: denied tool returns a recoverable ToolResult, not an exception ----
def test_denied_tool_returns_error_not_raise():
    from largestack._core.tools import ToolRegistry, ToolExecutor
    from largestack.types import ToolCall
    def secret() -> str:
        "secret"
        return "x"
    reg = ToolRegistry(); reg.register(secret)
    ex = ToolExecutor(reg, permissions={"deny": ["secret"]})
    r = asyncio.run(ex.execute(ToolCall(id="1", name="secret", params={})))
    assert r.error and r.content == ""  # did not raise


# ---- F-LLM-4: cost uses longest-prefix; unknown models price at 0 ----
def test_cost_longest_prefix():
    from largestack._core.cost import CostTracker
    ct = CostTracker()
    assert ct.calc("gpt-4o-mini", 1000, 1000) > 0
    assert ct.calc("totally-made-up-xyz", 1000, 1000) == 0.0


# ---- F-LLM-2 / F-LLM-3: structured native params for bare models + strictify ----
def test_structured_native_params_bare_model():
    from largestack._core.structured import build_native_params, _resolve_provider
    assert _resolve_provider("gpt-4o") == "openai"
    params = build_native_params("gpt-4o", {"type": "object", "properties": {"x": {"type": "string"}}})
    js = params["response_format"]["json_schema"]
    assert js["strict"] is False
    assert js["schema"]["additionalProperties"] is False  # strictified


# ---- F-ENG-1: cost budget is not triangular double-counted ----
def test_loop_guard_cost_delta_accumulation():
    from largestack._core.loop_guard import LoopGuard
    g = LoopGuard(cost_budget=10.0)
    # Engine passes per-turn deltas; 9 turns of 1.0 each => 9.0 total, no trip.
    for _ in range(9):
        g.check_cost(1.0)
    assert abs(g._cost - 9.0) < 1e-9  # exact, not 45.0 (triangular)


# ---- F-ORC-1: DAG cost budget actually engages ----
def test_dag_cost_budget_engages():
    from largestack._orchestrate.dag import DAGWorkflow
    dag = DAGWorkflow(cost_budget=1.0)

    def n1(state):
        return {**state, "n1_output": "a", "n1_cost": 100.0}

    def n2(state):
        return {**state, "n2_output": "b", "n2_cost": 100.0}

    dag.add_node("n1", n1)
    dag.add_node("n2", n2, deps=["n1"])
    out = asyncio.run(dag.run({}))
    assert out["_total_cost"] >= 100.0  # cost is tracked (was always 0.0)
    assert out.get("_budget_exceeded") is True  # budget tripped after n1


# ---- F-SEC-1: audit HMAC chain detects tampering by a DB-only attacker ----
def test_audit_hmac_detects_tamper():
    d = tempfile.mkdtemp()
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(os.path.join(d, "audit.db"))
    a.log("agent.run", "execute", agent_name="x", cost=999.0)
    a.log("agent.run", "execute", agent_name="y", cost=1.0)
    assert a.verify_integrity() == (True, None)
    raw = sqlite3.connect(os.path.join(d, "audit.db"))
    raw.execute("UPDATE audit_log SET cost=0.01 WHERE cost=999.0")
    raw.commit(); raw.close()
    ok, broken = a.verify_integrity()
    assert ok is False and broken is not None


# ---- F-SEC-2: SSRF — internal hosts blocked by name ----
def test_ssrf_blocks_internal_hosts():
    from largestack._security.network import public_only
    p = public_only()
    assert p.check("https://localhost/admin")[0] is False
    assert p.check("https://metadata.google.internal/x")[0] is False
    assert p.check("https://127.0.0.1/")[0] is False


# ---- F-SEC-3: sandbox scrubs env + AST import block ----
def test_sandbox_env_scrub_and_ast_block():
    from largestack._security.code_sandbox import CodeSandbox
    os.environ["LS_SECRET_PROBE"] = "topsecret"
    sb = CodeSandbox(backend="subprocess", timeout=5)
    r = asyncio.run(sb.execute(
        "import os; print('LEAK' if os.environ.get('LS_SECRET_PROBE') else 'CLEAN')"))
    assert "CLEAN" in r.stdout
    sb2 = CodeSandbox(backend="subprocess", timeout=5, allowed_imports=["math"])
    r2 = asyncio.run(sb2.execute("x=1; import os\nprint(os.getcwd())"))
    assert r2.exit_code == 1 and "Import blocked" in r2.stderr
    r3 = asyncio.run(sb2.execute('os = __import__("os")'))
    assert r3.exit_code == 1


# ---- F-SEC-4: ToolAccessPolicy param validation uses fullmatch ----
def test_tool_access_fullmatch():
    from largestack._guard.tool_access import ToolAccessPolicy
    p = ToolAccessPolicy()
    p.validate_params("sh", {"cmd": r"(ls|cat)( [\w./-]+)*"})
    assert p.check_params("sh", {"cmd": "ls -la"})[0] is True
    assert p.check_params("sh", {"cmd": "ls; rm -rf ~"})[0] is False


# ---- F-SEC-7: inter-agent auth has no public default secret ----
def test_inter_agent_auth_no_public_default():
    from largestack._guard.inter_agent_auth import InterAgentAuth
    a, b = InterAgentAuth(), InterAgentAuth()  # no secret -> random per instance
    msg = a.sign_message("a1", "a2", "hi")
    assert b.verify_message(msg)[0] is False  # different random secrets


# ---- F-SEC-10: separator-free SSN redacted with context ----
def test_pii_ssn_no_separator():
    from largestack._guard.pii import PIIGuard
    g = PIIGuard(entities=["ssn"])
    out = g.redact("My SSN: 123456789 is private")
    assert "123456789" not in out and "SSN" in out


# ---- F-INT-1 / F-INT-3: webhook fails closed; license keys are Ed25519-signed ----
def test_payment_failclosed_and_ed25519():
    d = tempfile.mkdtemp()
    from largestack._enterprise.payment import PaymentWebhook
    pw = PaymentWebhook(provider="lemonsqueezy", signing_secret="", db_path=os.path.join(d, "l.db"))
    assert pw.verify_signature(b"{}", "") is False  # no secret -> reject
    pw.allow_unsigned = True
    assert pw.verify_signature(b"{}", "") is True
    res = pw.generate_manual_key("u@test.com", "professional")
    key = res.get("license_key") or res.get("key")
    assert pw.verify_key_signature(str(key)) is True
    assert pw.verify_key_signature(str(key)[:-3] + "AAA") is False


# ---- F-INT-2: billing record() keyword form works + cost not dropped ----
def test_billing_record_keyword():
    d = tempfile.mkdtemp()
    from largestack._enterprise.billing import UsageMeter
    um = UsageMeter(db_path=os.path.join(d, "b.db"))
    um.record("u1", input_tokens=100, output_tokens=50, cost=0.25)  # documented kw form
    um.record("u2", cost=0.9)  # cost-only must not be zeroed
    rows = um.db.execute("SELECT SUM(cost) FROM usage").fetchone()
    assert abs(rows[0] - 1.15) < 1e-9


# ---- F-ORC-2: Flow does not re-fire listeners on repeated run() ----
def test_flow_no_duplicate_listeners():
    from largestack._orchestrate.flows import Flow
    f = Flow()
    calls = []

    @f.start
    async def start(x):
        await f.emit("done", x)
        return x

    @f.listen("done")
    async def on_done(evt):
        calls.append(1)

    asyncio.run(f.run(1))
    asyncio.run(f.run(2))
    assert len(calls) == 2  # one per run, not 1+2=3


# ---- F-ORC-5: supervisor one_for_all / rest_for_one no longer raise ----
def test_supervisor_strategies():
    from largestack._orchestrate.supervisor import Supervisor
    async def good():
        return "ok"
    for strat in ("one_for_all", "rest_for_one", "one_for_one"):
        sv = Supervisor(strategy=strat, children=[good, good])
        results = asyncio.run(sv.start())
        assert results == ["ok", "ok"]


# ---- F-ORC-4: saga resume skips completed steps ----
def test_saga_resume():
    d = tempfile.mkdtemp()
    from largestack._distributed.saga import SagaOrchestrator
    ran = []

    def step_a(ctx):
        ran.append("a"); return {"a": 1}

    def boom(ctx):
        ran.append("b"); raise RuntimeError("crash")

    s = SagaOrchestrator("t", persist_to=os.path.join(d, "s.db"))
    s.add_step("a", step_a)
    s.add_step("b", boom)
    with pytest.raises(Exception):
        asyncio.run(s.execute({}, saga_id="run1"))
    assert ran == ["a", "b"]
    # Resume: step "a" already completed -> not re-run; only "b" retried.
    ran.clear()
    s2 = SagaOrchestrator("t", persist_to=os.path.join(d, "s.db"))
    s2.add_step("a", step_a)
    s2.add_step("b", boom)
    with pytest.raises(Exception):
        asyncio.run(s2.execute({}, saga_id="run1", resume=True))
    assert ran == ["b"]  # "a" skipped on resume


# ---- F-RAG-1: dense embeddings get wired into the retriever ----
def test_rag_dense_embeddings_wired():
    from largestack.rag import create_rag
    # deterministic fake sync embedder (no model download)
    def fake_embed(text: str):
        return [float(text.count("a")), float(len(text)), 1.0]
    rag = create_rag(["alpha apple", "beta", "gamma"], top_k=2, embed_fn=fake_embed)
    assert rag.retriever._embeddings is not None  # hybrid wired (was always None)
    assert len(rag.retriever._embeddings) == 3


# ---- F-OBS-6: Google AIza keys are redacted from logs/traces ----
def test_redaction_covers_google_key():
    from largestack._observe.log_redaction import _redact_text
    s = "key=AIzaSyA1234567890abcdefghijklmnopqrstuvw"
    assert "AIza" not in _redact_text(s)
