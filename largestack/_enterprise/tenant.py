"""Multi-tenant isolation — per-tenant config, limits, and data.

v0.3.6: `current` tenant is now backed by a ContextVar instead of a shared
mutable attribute. Concurrent runs on the same TenantManager instance no
longer overwrite each other's "current tenant" — each async task gets its
own ContextVar value.
"""
from __future__ import annotations
import logging, time
from contextvars import ContextVar
from typing import Any

log = logging.getLogger("largestack.tenant")

# v0.3.6: per-async-task current tenant. Replaces the previous instance attribute
# `self._current` which leaked across concurrent runs.
_current_tenant_var: ContextVar[str | None] = ContextVar("largestack_current_tenant", default=None)

class Tenant:
    def __init__(self, tenant_id: str, name: str = "", tier: str = "free",
                 config: dict = None, rate_limits: dict = None,
                 allowed_models: list[str] = None, allowed_tools: list[str] = None):
        self.tenant_id = tenant_id
        self.name = name or tenant_id
        self.tier = tier  # 'free', 'pro', 'enterprise'
        self.config = config or {}
        self.rate_limits = rate_limits or self._default_limits(tier)
        self.allowed_models = allowed_models
        self.allowed_tools = allowed_tools
        self.created_at = time.time()
        self.active = True
    
    @staticmethod
    def _default_limits(tier: str) -> dict:
        return {
            "free": {"requests_per_minute": 10, "requests_per_day": 1000, "max_cost_per_day": 5.0},
            "pro": {"requests_per_minute": 60, "requests_per_day": 10000, "max_cost_per_day": 100.0},
            "enterprise": {"requests_per_minute": 600, "requests_per_day": 100000, "max_cost_per_day": 10000.0},
        }.get(tier, {"requests_per_minute": 10, "requests_per_day": 1000})


class TenantManager:
    """Manage tenant registration, isolation, and access control."""
    def __init__(self):
        self._tenants: dict[str, Tenant] = {}
        self._rate_tracker: dict[str, list[float]] = {}  # tenant_id → [timestamps]
    
    def register(self, tenant_id: str, config: dict = None, name: str = "",
                 tier: str = "free", **kwargs) -> Tenant:
        """Register a tenant. Accepts either config dict (legacy) or kwargs."""
        # Merge legacy config dict into kwargs
        if config:
            name = config.get("name", name)
            tier = config.get("plan", config.get("tier", tier))
            # Pass remaining config entries (max_agents, etc.) to Tenant.config
            extra = {k: v for k, v in config.items() if k not in ("name", "plan", "tier")}
            kwargs.setdefault("config", {}).update(extra)
        t = Tenant(tenant_id, name, tier, **kwargs)
        self._tenants[tenant_id] = t
        log.info(f"Tenant registered: {tenant_id} (tier={tier})")
        return t
    
    def get(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)
    
    def deactivate(self, tenant_id: str):
        t = self._tenants.get(tenant_id)
        if t: t.active = False
    
    def check_rate_limit(self, tenant_id: str) -> tuple[bool, str]:
        t = self._tenants.get(tenant_id)
        if not t or not t.active: return False, "Tenant not found or inactive"
        
        now = time.time()
        self._rate_tracker.setdefault(tenant_id, [])
        # Prune old timestamps
        self._rate_tracker[tenant_id] = [ts for ts in self._rate_tracker[tenant_id] if now - ts < 60]
        
        rpm = t.rate_limits.get("requests_per_minute", 60)
        if len(self._rate_tracker[tenant_id]) >= rpm:
            return False, f"Rate limit: {rpm}/min exceeded"
        
        self._rate_tracker[tenant_id].append(now)
        return True, ""
    
    def check_model_allowed(self, tenant_id: str, model: str) -> bool:
        t = self._tenants.get(tenant_id)
        if not t: return False
        if not t.allowed_models: return True  # No restriction
        return any(m in model for m in t.allowed_models)
    
    def check_tool_allowed(self, tenant_id: str, tool_name: str) -> bool:
        t = self._tenants.get(tenant_id)
        if not t: return False
        if not t.allowed_tools: return True
        return tool_name in t.allowed_tools
    

    def set_current(self, tenant_id: str):
        """Set the current active tenant for this async task only.
        
        v0.3.6: backed by ContextVar, so concurrent agent runs each see
        their own current tenant without stomping on each other.
        Returns the ContextVar token so callers can reset() if needed,
        but most callers just rely on async-task scoping.
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant not registered: {tenant_id}")
        return _current_tenant_var.set(tenant_id)
    
    def reset_current(self, token=None) -> None:
        """Reset current tenant. Pass the token returned from set_current()."""
        if token is not None:
            _current_tenant_var.reset(token)
        else:
            # Best-effort: set to None
            _current_tenant_var.set(None)
    
    @property
    def current(self) -> str | None:
        """Current active tenant for this async task."""
        return _current_tenant_var.get()

    def get_config(self, tenant_id: str = None) -> dict:
        """Get config for a tenant (or current tenant if not specified)."""
        tid = tenant_id or self.current
        if not tid:
            return {}
        t = self._tenants.get(tid)
        if not t:
            return {}
        # Flatten: expose tier as 'plan' + all config fields
        result = {"plan": t.tier, "tier": t.tier, "name": t.name, "active": t.active}
        result.update(t.config or {})
        return result

    def list_tenants(self) -> list[dict]:
        return [{"id": t.tenant_id, "name": t.name, "tier": t.tier, "active": t.active}
                for t in self._tenants.values()]
