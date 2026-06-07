"""Risk-aware tool action policy decisions."""

from __future__ import annotations

import json
import re
from typing import Any

from largestack._guard.config import GuardrailConfig, get_guardrail_config
from largestack._guard.pii import SECRET_PATTERNS
from largestack._guard.policy import (
    GuardrailDecision,
    GuardrailRiskType,
    GuardrailSeverity,
    allow,
    block,
    require_approval,
    warn,
)


READ_ACTIONS = ("read", "get", "fetch", "search", "retrieve", "list", "query", "inspect")
WRITE_ACTIONS = ("write", "create", "update", "insert", "save", "patch", "modify", "upsert")
DELETE_ACTIONS = ("delete", "remove", "drop", "truncate", "destroy", "purge")
SEND_ACTIONS = ("send", "email", "message", "notify", "post", "publish")
UPLOAD_ACTIONS = ("upload", "export", "share", "forward")
PAYMENT_ACTIONS = ("payment", "pay", "refund", "transfer", "payout", "charge", "invoice")

SENSITIVE_PARAM_RE = re.compile(
    r"\b(secret|token|password|api[_-]?key|credential|aadhaar|pan|card|customer|pii)\b",
    re.I,
)


def decide_tool_action(
    tool_name: str,
    params: dict[str, Any] | None = None,
    *,
    config: GuardrailConfig | None = None,
) -> GuardrailDecision:
    """Return the policy decision for a tool call.

    This function does not execute approval. It returns a decision that callers
    or future HITL integrations can enforce.
    """
    cfg = config or get_guardrail_config()
    params = params or {}
    name = tool_name.lower()
    text = _params_text(params)

    if _is_external_upload(name) and _contains_sensitive(text):
        return block(
            "External upload of sensitive data is blocked",
            risk_type=GuardrailRiskType.EXTERNAL_EXFILTRATION,
            severity=GuardrailSeverity.CRITICAL,
            metadata={"tool": tool_name, "context": cfg.context},
        )

    if _contains_any(name, PAYMENT_ACTIONS):
        metadata = {"tool": tool_name, "context": cfg.context}
        if cfg.mode.value == "strict" or cfg.context == "bfsi":
            metadata["maker_checker"] = True
        return require_approval(
            "Payment or fund movement requires approval",
            risk_type=GuardrailRiskType.UNSAFE_TOOL,
            severity=GuardrailSeverity.CRITICAL,
            metadata=metadata,
        )

    if _contains_any(name, DELETE_ACTIONS):
        if cfg.mode.value == "strict" or cfg.context == "bfsi":
            return block(
                "Delete/destructive tool action blocked in strict mode",
                risk_type=GuardrailRiskType.UNSAFE_TOOL,
                severity=GuardrailSeverity.HIGH,
                metadata={"tool": tool_name, "context": cfg.context},
            )
        return require_approval(
            "Delete/destructive tool action requires approval",
            risk_type=GuardrailRiskType.UNSAFE_TOOL,
            severity=GuardrailSeverity.HIGH,
            metadata={"tool": tool_name, "context": cfg.context},
        )

    if _contains_any(name, WRITE_ACTIONS + SEND_ACTIONS + UPLOAD_ACTIONS):
        return require_approval(
            "State-changing or outbound tool action requires approval",
            risk_type=GuardrailRiskType.UNSAFE_TOOL,
            severity=GuardrailSeverity.HIGH,
            metadata={"tool": tool_name, "context": cfg.context},
        )

    if _contains_any(name, READ_ACTIONS):
        return allow(
            "Read-only tool action allowed",
            risk_type=GuardrailRiskType.UNSAFE_TOOL,
            severity=GuardrailSeverity.LOW,
            metadata={"tool": tool_name, "context": cfg.context},
        )

    return warn(
        "Unknown tool impact; review recommended",
        risk_type=GuardrailRiskType.UNSAFE_TOOL,
        severity=GuardrailSeverity.MEDIUM,
        metadata={"tool": tool_name, "context": cfg.context},
    )


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_external_upload(name: str) -> bool:
    return _contains_any(name, SEND_ACTIONS + UPLOAD_ACTIONS) or "http" in name or "api" in name


def _contains_sensitive(text: str) -> bool:
    if SENSITIVE_PARAM_RE.search(text):
        return True
    return any(pat.search(text) for pat in SECRET_PATTERNS.values())


def _params_text(params: dict[str, Any]) -> str:
    try:
        return json.dumps(params, sort_keys=True, default=str)
    except Exception:
        return str(params)
