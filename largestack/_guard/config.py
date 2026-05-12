"""Guardrail configuration resolved from environment variables."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os

from largestack._guard.policy import GuardrailAction, GuardrailMode

log = logging.getLogger("largestack.guard.config")


@dataclass(frozen=True)
class GuardrailConfig:
    mode: GuardrailMode = GuardrailMode.PROTECT
    context: str = "general"
    pii_action: GuardrailAction = GuardrailAction.WARN
    secret_action: GuardrailAction = GuardrailAction.REDACT
    financial_data_action: GuardrailAction = GuardrailAction.REDACT
    prompt_injection_action: GuardrailAction = GuardrailAction.WARN
    tool_write_action: GuardrailAction = GuardrailAction.REQUIRE_APPROVAL
    external_upload_action: GuardrailAction = GuardrailAction.BLOCK
    critical_risk_action: GuardrailAction = GuardrailAction.BLOCK
    bfsi_approved_providers: tuple[str, ...] = ()


_ACTION_DEFAULTS = {
    "LARGESTACK_PII_ACTION": GuardrailAction.WARN,
    "LARGESTACK_SECRET_ACTION": GuardrailAction.REDACT,
    "LARGESTACK_FINANCIAL_DATA_ACTION": GuardrailAction.REDACT,
    "LARGESTACK_PROMPT_INJECTION_ACTION": GuardrailAction.WARN,
    "LARGESTACK_TOOL_WRITE_ACTION": GuardrailAction.REQUIRE_APPROVAL,
    "LARGESTACK_EXTERNAL_UPLOAD_ACTION": GuardrailAction.BLOCK,
    "LARGESTACK_CRITICAL_RISK_ACTION": GuardrailAction.BLOCK,
}


def _parse_mode(value: str | None, default: GuardrailMode = GuardrailMode.PROTECT) -> GuardrailMode:
    if not value:
        return default
    try:
        return GuardrailMode(value.strip().lower())
    except ValueError:
        log.warning("Invalid LARGESTACK_GUARDRAIL_MODE=%r; falling back to %s", value, default.value)
        return default


def _parse_action(env_name: str) -> GuardrailAction:
    default = _ACTION_DEFAULTS[env_name]
    value = os.environ.get(env_name)
    if not value:
        return default
    try:
        return GuardrailAction(value.strip().lower())
    except ValueError:
        log.warning("Invalid %s=%r; falling back to %s", env_name, value, default.value)
        return default


def _parse_providers(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(p.strip() for p in value.split(",") if p.strip())


def get_guardrail_config() -> GuardrailConfig:
    """Resolve guardrail policy config from the current process environment."""
    context = (os.environ.get("LARGESTACK_CONTEXT") or "general").strip().lower() or "general"
    mode = _parse_mode(os.environ.get("LARGESTACK_GUARDRAIL_MODE"))
    if "LARGESTACK_GUARDRAIL_MODE" not in os.environ and context == "bfsi":
        mode = GuardrailMode.STRICT
    return GuardrailConfig(
        mode=mode,
        context=context,
        pii_action=_parse_action("LARGESTACK_PII_ACTION"),
        secret_action=_parse_action("LARGESTACK_SECRET_ACTION"),
        financial_data_action=_parse_action("LARGESTACK_FINANCIAL_DATA_ACTION"),
        prompt_injection_action=_parse_action("LARGESTACK_PROMPT_INJECTION_ACTION"),
        tool_write_action=_parse_action("LARGESTACK_TOOL_WRITE_ACTION"),
        external_upload_action=_parse_action("LARGESTACK_EXTERNAL_UPLOAD_ACTION"),
        critical_risk_action=_parse_action("LARGESTACK_CRITICAL_RISK_ACTION"),
        bfsi_approved_providers=_parse_providers(os.environ.get("LARGESTACK_BFSI_APPROVED_PROVIDERS")),
    )
