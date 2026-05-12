"""v0.5.0: Per-tenant DB scoping for billing + RBAC.

Multi-tenant SaaS requires safe defaults: forgetting to pass tenant_id
must FAIL LOUD, not silently leak data across tenants.
"""
from __future__ import annotations

import pytest


# ---------- billing tenant scoping ----------

def test_usage_meter_get_for_current_tenant_requires_context():
    """Without a tenant context, the safe-default method must raise."""
    from largestack._enterprise.billing import UsageMeter
    from largestack._enterprise.tenant import _current_tenant_var

    # Ensure no tenant context
    _current_tenant_var.set(None)

    meter = UsageMeter()  # in-memory
    with pytest.raises(ValueError, match="No tenant context"):
        meter.get_usage_for_current_tenant()


def test_usage_meter_record_for_current_tenant_requires_context():
    from largestack._enterprise.billing import UsageMeter
    from largestack._enterprise.tenant import _current_tenant_var

    _current_tenant_var.set(None)
    meter = UsageMeter()
    with pytest.raises(ValueError, match="No tenant context"):
        meter.record_for_current_tenant(user_id="alice", cost=0.05)


def test_usage_meter_scoped_record_and_query_isolates_tenants():
    """Tenant A's usage must not appear in tenant B's query."""
    from largestack._enterprise.billing import UsageMeter
    from largestack._enterprise.tenant import _current_tenant_var

    meter = UsageMeter()

    # Tenant A records
    tok = _current_tenant_var.set("acme")
    try:
        meter.record_for_current_tenant(
            user_id="alice", cost=1.0, model="gpt-4o"
        )
        meter.record_for_current_tenant(
            user_id="alice", cost=2.5, model="gpt-4o"
        )
    finally:
        _current_tenant_var.reset(tok)

    # Tenant B records
    tok = _current_tenant_var.set("globex")
    try:
        meter.record_for_current_tenant(
            user_id="bob", cost=10.0, model="claude-3-5-sonnet"
        )
    finally:
        _current_tenant_var.reset(tok)

    # Query Tenant A in context — sees only A's spend
    tok = _current_tenant_var.set("acme")
    try:
        u = meter.get_usage_for_current_tenant()
        assert u["request_count"] == 2
        assert abs(u["total_cost"] - 3.5) < 0.001  # 1.0 + 2.5
    finally:
        _current_tenant_var.reset(tok)

    # Query Tenant B in context — sees only B's spend
    tok = _current_tenant_var.set("globex")
    try:
        u = meter.get_usage_for_current_tenant()
        assert u["request_count"] == 1
        assert abs(u["total_cost"] - 10.0) < 0.001
    finally:
        _current_tenant_var.reset(tok)


def test_usage_meter_legacy_api_still_works():
    """Backwards compat: explicit tenant_id arg still accepted."""
    from largestack._enterprise.billing import UsageMeter

    meter = UsageMeter()
    meter.record(user_id="x", cost=5.0, tenant_id="acme")
    u = meter.get_usage(tenant_id="acme")
    assert u["request_count"] == 1


# ---------- RBAC tenant scoping ----------

def test_rbac_users_isolated_per_tenant():
    """Same user_id in different tenants must be separate identities."""
    from largestack._enterprise.rbac import RBAC

    rbac = RBAC()
    # Both tenants have an "alice" — completely different people
    rbac.add_user_for_tenant("acme", "alice", roles=["admin"])
    rbac.add_user_for_tenant("globex", "alice", roles=["viewer"])

    # Acme alice has admin
    assert rbac.check_for_tenant("acme", "alice", "agent.delete") is True
    # Globex alice does NOT have admin
    assert rbac.check_for_tenant("globex", "alice", "agent.delete") is False
    # And vice versa for viewer permissions
    assert rbac.check_for_tenant("globex", "alice", "agent.read") is True


def test_rbac_check_for_current_tenant_requires_context():
    from largestack._enterprise.rbac import RBAC
    from largestack._enterprise.tenant import _current_tenant_var

    _current_tenant_var.set(None)
    rbac = RBAC()
    rbac.add_user_for_tenant("acme", "alice", roles=["admin"])

    with pytest.raises(ValueError, match="No tenant context"):
        rbac.check_for_current_tenant("alice", "agent.run")


def test_rbac_check_for_current_tenant_uses_contextvar():
    from largestack._enterprise.rbac import RBAC
    from largestack._enterprise.tenant import _current_tenant_var

    rbac = RBAC()
    rbac.add_user_for_tenant("acme", "alice", roles=["admin"])
    rbac.add_user_for_tenant("globex", "alice", roles=["viewer"])

    tok = _current_tenant_var.set("acme")
    try:
        assert rbac.check_for_current_tenant("alice", "agent.delete") is True
    finally:
        _current_tenant_var.reset(tok)

    tok = _current_tenant_var.set("globex")
    try:
        assert rbac.check_for_current_tenant("alice", "agent.delete") is False
    finally:
        _current_tenant_var.reset(tok)


def test_rbac_list_users_for_tenant():
    from largestack._enterprise.rbac import RBAC

    rbac = RBAC()
    rbac.add_user_for_tenant("acme", "alice", roles=["admin"])
    rbac.add_user_for_tenant("acme", "bob", roles=["viewer"])
    rbac.add_user_for_tenant("globex", "carol", roles=["admin"])

    acme_users = sorted(rbac.list_users_for_tenant("acme"))
    assert acme_users == ["alice", "bob"]

    globex_users = rbac.list_users_for_tenant("globex")
    assert globex_users == ["carol"]


def test_rbac_legacy_unscoped_users_still_work():
    """Legacy tenant-less users must still function (no scoping)."""
    from largestack._enterprise.rbac import RBAC

    rbac = RBAC()
    rbac.add_user("legacy_user", roles=["admin"])
    assert rbac.check("legacy_user", "agent.delete") is True
