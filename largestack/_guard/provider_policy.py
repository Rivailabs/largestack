"""Provider routing policy for regulated/sensitive contexts."""
from __future__ import annotations

from largestack._guard.config import GuardrailConfig, get_guardrail_config
from largestack._guard.pii import PIIGuard
from largestack._guard.policy import GuardrailRiskType, GuardrailSeverity, allow, block, redact


def decide_provider_routing(
    provider: str,
    text: str,
    *,
    config: GuardrailConfig | None = None,
):
    """Decide whether a provider may receive the given payload."""
    cfg = config or get_guardrail_config()
    guard = PIIGuard()
    sensitive = guard._detect_any(text) or guard._detect_secret(text) or guard._detect_financial(text)

    if not sensitive:
        return allow(
            "Provider routing allowed",
            risk_type=GuardrailRiskType.PROVIDER_ROUTING_VIOLATION,
            severity=GuardrailSeverity.LOW,
            metadata={"provider": provider, "context": cfg.context},
        )

    regulated = cfg.mode.value == "strict" or cfg.context == "bfsi"
    approved = not cfg.bfsi_approved_providers or provider in cfg.bfsi_approved_providers
    if regulated and not approved:
        return block(
            "Sensitive data cannot be routed to an unapproved provider",
            risk_type=GuardrailRiskType.PROVIDER_ROUTING_VIOLATION,
            severity=GuardrailSeverity.CRITICAL,
            metadata={"provider": provider, "context": cfg.context, "approved_providers": cfg.bfsi_approved_providers},
        )

    if regulated:
        return redact(
            "Sensitive data must be redacted before provider call",
            redacted_text=guard.redact_financial(guard.redact(text)),
            risk_type=GuardrailRiskType.PROVIDER_ROUTING_VIOLATION,
            severity=GuardrailSeverity.HIGH,
            metadata={"provider": provider, "context": cfg.context, "audit": True},
        )

    return allow(
        "Provider routing allowed",
        risk_type=GuardrailRiskType.PROVIDER_ROUTING_VIOLATION,
        severity=GuardrailSeverity.MEDIUM,
        metadata={"provider": provider, "context": cfg.context},
    )
