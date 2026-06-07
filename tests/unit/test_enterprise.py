"""Tests for enterprise features."""

import asyncio, tempfile, os
from largestack._enterprise.rbac import RBAC
from largestack._enterprise.audit import AuditTrail
from largestack._enterprise.tenant import TenantManager
from largestack._enterprise.billing import UsageMeter
from largestack._enterprise.canary import CanaryDeployment
from largestack._distributed.event_sourcing import EventStore
from largestack._distributed.saga import SagaOrchestrator


def test_rbac_roles():
    r = RBAC()
    r.assign_role("alice", "admin")
    r.assign_role("bob", "viewer")
    assert r.check("alice", "agent.create")
    assert r.check("bob", "trace.view")
    assert not r.check("bob", "agent.create")


def test_rbac_custom_role():
    r = RBAC()
    r.add_role("analyst", ["trace.view", "cost.view", "agent.view"])
    r.assign_role("charlie", "analyst")
    assert r.check("charlie", "cost.view")
    assert not r.check("charlie", "agent.create")


def test_audit_trail():
    at = AuditTrail(os.path.join(tempfile.mkdtemp(), "audit.db"))
    at.log("agent.run", "execute", agent_name="test", cost=0.05, trace_id="abc123")
    at.log("tool.call", "web_search", agent_name="test")
    assert at.count() == 2
    assert at.count("test") == 2
    entries = at.query(agent_name="test")
    assert len(entries) == 2


def test_tenant():
    tm = TenantManager()
    tm.register("acme", {"plan": "enterprise", "max_agents": 100})
    tm.register("startup", {"plan": "pro"})
    tm.set_current("acme")
    assert tm.current == "acme"
    assert tm.get_config()["plan"] == "enterprise"


def test_billing():
    um = UsageMeter()
    um.record("acme", 10000, 5000, 0.50)
    um.record("acme", 5000, 2000, 0.20)
    usage = um.get_usage("acme")
    assert usage["requests"] == 2
    assert usage["cost"] == 0.70


def test_canary():
    c = CanaryDeployment()
    assert c.current_percentage == 0.01  # First stage
    for _ in range(20):
        c.record_result("new", True)
    advanced = c.advance()
    assert advanced or c.current_percentage > 0.01


def test_event_sourcing():
    es = EventStore(os.path.join(tempfile.mkdtemp(), "events.db"))
    es.append("agent-1", "started", {"task": "hello"})
    es.append("agent-1", "tool_called", {"tool": "search", "result": "found"})
    es.append("agent-1", "completed", {"answer": "world"})
    events = es.get_stream("agent-1")
    assert len(events) == 3
    state = es.reconstruct_state("agent-1")
    assert state["answer"] == "world"


def test_saga():
    compensated = []
    s = SagaOrchestrator("test-saga")
    s.add_step("step1", lambda c: {**c, "step1": True}, lambda c: compensated.append("step1"))
    s.add_step("step2", lambda c: {**c, "step2": True}, lambda c: compensated.append("step2"))
    r = asyncio.run(s.execute({}))
    assert r["step1"] and r["step2"]
    assert len(compensated) == 0  # No failures


def test_saga_with_failure():
    compensated = []
    s = SagaOrchestrator("fail-saga")
    s.add_step("step1", lambda c: {**c, "s1": True}, lambda c: compensated.append("s1"))

    def fail(c):
        raise RuntimeError("boom")

    s.add_step("step2", fail, lambda c: compensated.append("s2"))
    try:
        asyncio.run(s.execute({}))
        assert False, "Should have raised"
    except RuntimeError:
        pass
    assert "s1" in compensated  # Step1 was compensated
