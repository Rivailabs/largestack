"""Per-agent permission boundaries with hierarchical policy enforcement."""

from __future__ import annotations
import logging, time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("largestack.permissions")


class CheckResult:
    """Permission check result — works as bool AND tuple (allowed, reason)."""

    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

    def __bool__(self):
        return self.allowed

    def __iter__(self):
        yield self.allowed
        yield self.reason

    def __repr__(self):
        return f"CheckResult(allowed={self.allowed}, reason={self.reason!r})"


@dataclass
class Permissions:
    """Agent permission boundaries.

    Controls what an agent can and cannot do beyond tool-level permissions.
    Policies are checked at runtime; violations logged to audit trail.
    """

    # Core capabilities
    can_spawn_agents: bool = True
    can_write_state: bool = True
    can_send_email: bool = False
    can_execute_code: bool = True
    can_access_network: bool = True
    can_read_filesystem: bool = True
    can_write_filesystem: bool = False

    # Data access
    can_access_knowledge: list[str] = field(default_factory=list)  # Empty = all
    can_access_memory: list[str] = field(default_factory=list)  # Memory types allowed
    data_classifications: list[str] = field(
        default_factory=lambda: ["public"]
    )  # public/internal/confidential/restricted

    # Resource limits
    max_cost_per_run: float = 5.0
    max_tool_calls_per_run: int = 100
    max_tokens_per_run: int = 100000
    max_duration_seconds: float = 600.0
    max_parallel_tasks: int = 5

    # Approval workflow
    require_approval_for: list[str] = field(default_factory=list)
    approval_callback: Callable = None

    # Rate limits
    rate_limit_per_minute: int = 60
    rate_limit_per_day: int = 10000

    # Network policy
    allowed_domains: list[str] = field(default_factory=list)  # Empty = all allowed
    blocked_domains: list[str] = field(default_factory=list)

    def check(self, action: str, **kw) -> tuple[bool, str]:
        """Check if action is permitted. Returns (allowed, reason_if_denied)."""

        # Core capability checks
        capability_map = {
            "spawn_agent": ("can_spawn_agents", "Agent spawning disabled"),
            "write_state": ("can_write_state", "State writes disabled"),
            "send_email": ("can_send_email", "Email sending disabled"),
            "execute_code": ("can_execute_code", "Code execution disabled"),
            "access_network": ("can_access_network", "Network access disabled"),
            "read_filesystem": ("can_read_filesystem", "Filesystem reads disabled"),
            "write_filesystem": ("can_write_filesystem", "Filesystem writes disabled"),
        }

        if action in capability_map:
            attr, msg = capability_map[action]
            if not getattr(self, attr):
                return CheckResult(False, msg)

        # Knowledge access
        if action == "access_knowledge":
            resource = kw.get("resource", "")
            if self.can_access_knowledge and resource not in self.can_access_knowledge:
                return CheckResult(False, f"Knowledge resource not allowed: {resource}")

        # Memory access
        if action == "access_memory":
            mem_type = kw.get("memory_type", "")
            if self.can_access_memory and mem_type not in self.can_access_memory:
                return CheckResult(False, f"Memory type not allowed: {mem_type}")

        # Data classification
        if action == "access_data":
            classification = kw.get("classification", "public")
            if classification not in self.data_classifications:
                return CheckResult(False, f"Classification level '{classification}' not permitted")

        # Network policy
        if action == "network_request":
            domain = kw.get("domain", "")
            if domain in self.blocked_domains:
                return CheckResult(False, f"Domain blocked: {domain}")
            if self.allowed_domains and domain not in self.allowed_domains:
                return CheckResult(False, f"Domain not in allowlist: {domain}")

        # Approval-required actions
        if action in self.require_approval_for:
            if self.approval_callback:
                approved = self.approval_callback(action, **kw)
                if not approved:
                    return CheckResult(False, f"Approval denied for: {action}")
            else:
                return CheckResult(False, f"Action requires approval (no callback set): {action}")

        return CheckResult(True, "")

    def check_resource_limits(
        self, current_cost: float = 0, tool_calls: int = 0, tokens: int = 0, duration_s: float = 0
    ) -> tuple[bool, str]:
        """Check if current resource usage is within limits."""
        if current_cost > self.max_cost_per_run:
            return CheckResult(
                False, f"Cost limit exceeded: ${current_cost:.4f} > ${self.max_cost_per_run}"
            )
        if tool_calls > self.max_tool_calls_per_run:
            return CheckResult(
                False, f"Tool call limit exceeded: {tool_calls} > {self.max_tool_calls_per_run}"
            )
        if tokens > self.max_tokens_per_run:
            return CheckResult(False, f"Token limit exceeded: {tokens} > {self.max_tokens_per_run}")
        if duration_s > self.max_duration_seconds:
            return CheckResult(
                False, f"Duration limit exceeded: {duration_s:.1f}s > {self.max_duration_seconds}s"
            )
        return CheckResult(True, "")


class PermissionEnforcer:
    """Runtime permission enforcer with audit logging.

    Wraps an agent's operations to enforce permissions and log violations.

        enforcer = PermissionEnforcer(permissions)
        allowed, reason = enforcer.check("send_email", to="user@example.com")
    """

    def __init__(self, permissions: Permissions, audit_enabled: bool = True):
        self.permissions = permissions
        self.audit_enabled = audit_enabled
        self._audit: list[dict] = []
        self._violation_count = 0

    def check(self, action: str, **kw) -> tuple[bool, str]:
        allowed, reason = self.permissions.check(action, **kw)
        if self.audit_enabled:
            self._audit.append(
                {
                    "timestamp": time.time(),
                    "action": action,
                    "allowed": allowed,
                    "reason": reason,
                    "context": kw,
                }
            )
        if not allowed:
            self._violation_count += 1
            log.warning(f"Permission denied: {action} — {reason}")
        return allowed, reason

    def enforce(self, action: str, **kw):
        """Check and raise if denied."""
        allowed, reason = self.check(action, **kw)
        if not allowed:
            raise PermissionError(f"Action '{action}' denied: {reason}")

    def get_audit_log(self, since: float = None) -> list[dict]:
        if since:
            return [a for a in self._audit if a["timestamp"] >= since]
        return list(self._audit)

    @property
    def violation_count(self) -> int:
        return self._violation_count

    @property
    def stats(self) -> dict:
        total = len(self._audit)
        denied = sum(1 for a in self._audit if not a["allowed"])
        return {
            "total_checks": total,
            "denied": denied,
            "allowed": total - denied,
            "violation_rate": denied / max(total, 1),
        }


# Preset policies
PRESET_POLICIES = {
    "strict": Permissions(
        can_spawn_agents=False,
        can_send_email=False,
        can_execute_code=False,
        can_write_filesystem=False,
        max_cost_per_run=1.0,
        max_tool_calls_per_run=20,
        data_classifications=["public"],
        require_approval_for=["network_request"],
    ),
    "standard": Permissions(),  # Defaults
    "trusted": Permissions(
        can_send_email=True,
        can_write_filesystem=True,
        max_cost_per_run=50.0,
        max_tool_calls_per_run=500,
        data_classifications=["public", "internal", "confidential"],
    ),
    "admin": Permissions(
        can_send_email=True,
        can_write_filesystem=True,
        max_cost_per_run=1000.0,
        max_tool_calls_per_run=10000,
        max_duration_seconds=3600,
        data_classifications=["public", "internal", "confidential", "restricted"],
    ),
}


def get_preset(name: str) -> Permissions:
    """Get a preset permission policy by name."""
    if name not in PRESET_POLICIES:
        raise ValueError(f"Unknown preset: {name}. Available: {list(PRESET_POLICIES.keys())}")
    return PRESET_POLICIES[name]
