"""Tests for enhanced enterprise modules."""

import sys, tempfile, os

sys.path.insert(0, ".")


def test_rbac_wildcard():
    from largestack._enterprise.rbac import RBAC

    r = RBAC()
    r.add_role("super", ["agent.*"])
    r.assign_role("alice", "super")
    assert r.check("alice", "agent.create")
    assert r.check("alice", "agent.delete")
    assert not r.check("alice", "billing.read")


def test_rbac_decorator():
    from largestack._enterprise.rbac import RBAC

    r = RBAC()
    r.assign_role("alice", "developer")

    @r.require("agent.create")
    def create_agent(user_id: str):
        return "created"

    assert create_agent(user_id="alice") == "created"
    try:
        create_agent(user_id="unknown")
        assert False
    except PermissionError:
        pass


def test_rbac_revoke():
    from largestack._enterprise.rbac import RBAC

    r = RBAC()
    r.assign_role("alice", "admin")
    assert r.check("alice", "agent.create")
    r.revoke("alice", "admin")
    assert not r.check("alice", "agent.create")


def test_rbac_audit_log():
    from largestack._enterprise.rbac import RBAC

    r = RBAC()
    r.assign_role("alice", "admin")
    r.check("alice", "agent.create")
    r.check("bob", "agent.delete")  # bob not registered
    logs = r.audit_log()
    assert len(logs) == 2
    assert logs[0]["allowed"] is True
    assert logs[1]["allowed"] is False


def test_billing_user_breakdown():
    from largestack._enterprise.billing import UsageMeter

    um = UsageMeter()
    um.record("alice", 1000, 500, 0.10, model="gpt-4o")
    um.record("bob", 2000, 1000, 0.20, model="gpt-4o")
    um.record("alice", 500, 200, 0.05, model="claude")
    top = um.get_top_users()
    assert top[0]["user_id"] == "bob"
    assert top[0]["cost"] == 0.20


def test_billing_by_model():
    from largestack._enterprise.billing import UsageMeter

    um = UsageMeter()
    um.record("alice", 1000, 500, 0.10, model="gpt-4o")
    um.record("alice", 1000, 500, 0.10, model="gpt-4o")
    um.record("alice", 1000, 500, 0.05, model="claude-haiku")
    breakdown = um.get_by_model()
    assert len(breakdown) == 2
    gpt4o = next(b for b in breakdown if b["model"] == "gpt-4o")
    assert gpt4o["requests"] == 2
    assert gpt4o["cost"] == 0.20


def test_budget_enforcer():
    from largestack._enterprise.billing import UsageMeter, BudgetEnforcer

    um = UsageMeter()
    be = BudgetEnforcer(um)
    be.set_limit("alice", daily=1.0)

    # Under budget
    allowed, _ = be.check("alice")
    assert allowed

    # Exceed budget
    um.record("alice", 1000, 500, 1.50)
    allowed, reason = be.check("alice")
    assert not allowed
    assert "budget" in reason.lower()


def test_tenant_tier_limits():
    from largestack._enterprise.tenant import TenantManager

    tm = TenantManager()
    tm.register("free-tenant", {"plan": "free"})
    tm.register("pro-tenant", {"plan": "pro"})
    tm.register("ent-tenant", {"plan": "enterprise"})

    free = tm.get("free-tenant")
    pro = tm.get("pro-tenant")
    ent = tm.get("ent-tenant")

    # Pro should have higher rate limit than free
    assert pro.rate_limits["requests_per_minute"] > free.rate_limits["requests_per_minute"]
    # Enterprise higher than pro
    assert ent.rate_limits["requests_per_minute"] > pro.rate_limits["requests_per_minute"]


def test_tenant_rate_limiting():
    from largestack._enterprise.tenant import TenantManager

    tm = TenantManager()
    t = tm.register("test", name="Test", tier="free")
    t.rate_limits["requests_per_minute"] = 3

    # First 3 allowed
    for i in range(3):
        allowed, _ = tm.check_rate_limit("test")
        assert allowed

    # 4th blocked
    allowed, reason = tm.check_rate_limit("test")
    assert not allowed
    assert "Rate limit" in reason


def test_tenant_model_allowlist():
    from largestack._enterprise.tenant import TenantManager

    tm = TenantManager()
    tm.register("restricted", tier="free", allowed_models=["gpt-4o-mini", "claude-haiku"])
    assert tm.check_model_allowed("restricted", "openai/gpt-4o-mini")
    assert not tm.check_model_allowed("restricted", "openai/gpt-4o")


def test_tenant_tool_allowlist():
    from largestack._enterprise.tenant import TenantManager

    tm = TenantManager()
    tm.register("limited", tier="free", allowed_tools=["search", "read"])
    assert tm.check_tool_allowed("limited", "search")
    assert not tm.check_tool_allowed("limited", "shell_exec")


def test_tenant_config_dict():
    from largestack._enterprise.tenant import TenantManager

    tm = TenantManager()
    tm.register("acme", {"plan": "enterprise", "max_agents": 100})
    tm.set_current("acme")
    cfg = tm.get_config()
    assert cfg["plan"] == "enterprise"
    assert cfg["max_agents"] == 100
