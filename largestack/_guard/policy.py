"""Central guardrail policy model.

This module defines the shared vocabulary for risk-aware guardrails. It is
intentionally behavior-free so existing guards can adopt it incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuardrailMode(str, Enum):
    OBSERVE = "observe"
    WARN = "warn"
    PROTECT = "protect"
    STRICT = "strict"
    CUSTOM = "custom"


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    REDACT = "redact"
    ISOLATE = "isolate"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class GuardrailSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailRiskType(str, Enum):
    PII = "pii"
    SECRET = "secret"
    FINANCIAL_DATA = "financial_data"
    PROMPT_INJECTION = "prompt_injection"
    UNSAFE_TOOL = "unsafe_tool"
    EXTERNAL_EXFILTRATION = "external_exfiltration"
    MALWARE = "malware"
    CREDENTIAL_THEFT = "credential_theft"
    ILLEGAL_ABUSE = "illegal_abuse"
    PROVIDER_ROUTING_VIOLATION = "provider_routing_violation"
    UNKNOWN = "unknown"


@dataclass
class GuardrailDecision:
    allowed: bool
    action: GuardrailAction
    severity: GuardrailSeverity
    risk_type: GuardrailRiskType
    message: str
    redacted_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def allow(
    message: str = "Allowed",
    *,
    risk_type: GuardrailRiskType = GuardrailRiskType.UNKNOWN,
    severity: GuardrailSeverity = GuardrailSeverity.LOW,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        action=GuardrailAction.ALLOW,
        severity=severity,
        risk_type=risk_type,
        message=message,
        metadata=metadata or {},
    )


def warn(
    message: str,
    *,
    risk_type: GuardrailRiskType = GuardrailRiskType.UNKNOWN,
    severity: GuardrailSeverity = GuardrailSeverity.MEDIUM,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        action=GuardrailAction.WARN,
        severity=severity,
        risk_type=risk_type,
        message=message,
        metadata=metadata or {},
    )


def redact(
    message: str,
    *,
    redacted_text: str | None = None,
    risk_type: GuardrailRiskType = GuardrailRiskType.UNKNOWN,
    severity: GuardrailSeverity = GuardrailSeverity.MEDIUM,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        action=GuardrailAction.REDACT,
        severity=severity,
        risk_type=risk_type,
        message=message,
        redacted_text=redacted_text,
        metadata=metadata or {},
    )


def isolate(
    message: str,
    *,
    risk_type: GuardrailRiskType = GuardrailRiskType.PROMPT_INJECTION,
    severity: GuardrailSeverity = GuardrailSeverity.MEDIUM,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        action=GuardrailAction.ISOLATE,
        severity=severity,
        risk_type=risk_type,
        message=message,
        metadata=metadata or {},
    )


def require_approval(
    message: str,
    *,
    risk_type: GuardrailRiskType = GuardrailRiskType.UNSAFE_TOOL,
    severity: GuardrailSeverity = GuardrailSeverity.HIGH,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=True,
        action=GuardrailAction.REQUIRE_APPROVAL,
        severity=severity,
        risk_type=risk_type,
        message=message,
        metadata=metadata or {},
    )


def block(
    message: str,
    *,
    risk_type: GuardrailRiskType = GuardrailRiskType.UNKNOWN,
    severity: GuardrailSeverity = GuardrailSeverity.CRITICAL,
    metadata: dict[str, Any] | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=False,
        action=GuardrailAction.BLOCK,
        severity=severity,
        risk_type=risk_type,
        message=message,
        metadata=metadata or {},
    )
