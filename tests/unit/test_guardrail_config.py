import logging

from largestack._guard.config import get_guardrail_config
from largestack._guard.policy import GuardrailAction, GuardrailMode


_ENV_NAMES = [
    "LARGESTACK_GUARDRAIL_MODE",
    "LARGESTACK_CONTEXT",
    "LARGESTACK_PII_ACTION",
    "LARGESTACK_SECRET_ACTION",
    "LARGESTACK_FINANCIAL_DATA_ACTION",
    "LARGESTACK_PROMPT_INJECTION_ACTION",
    "LARGESTACK_TOOL_WRITE_ACTION",
    "LARGESTACK_EXTERNAL_UPLOAD_ACTION",
    "LARGESTACK_CRITICAL_RISK_ACTION",
    "LARGESTACK_BFSI_APPROVED_PROVIDERS",
]


def _clear_env(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_guardrail_config_defaults(monkeypatch):
    _clear_env(monkeypatch)

    cfg = get_guardrail_config()

    assert cfg.mode == GuardrailMode.PROTECT
    assert cfg.context == "general"
    assert cfg.pii_action == GuardrailAction.WARN
    assert cfg.secret_action == GuardrailAction.REDACT
    assert cfg.financial_data_action == GuardrailAction.REDACT
    assert cfg.prompt_injection_action == GuardrailAction.WARN
    assert cfg.tool_write_action == GuardrailAction.REQUIRE_APPROVAL
    assert cfg.external_upload_action == GuardrailAction.BLOCK
    assert cfg.critical_risk_action == GuardrailAction.BLOCK
    assert cfg.bfsi_approved_providers == ()


def test_guardrail_config_env_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "observe")
    monkeypatch.setenv("LARGESTACK_CONTEXT", "planning")
    monkeypatch.setenv("LARGESTACK_PII_ACTION", "redact")
    monkeypatch.setenv("LARGESTACK_PROMPT_INJECTION_ACTION", "isolate")
    monkeypatch.setenv("LARGESTACK_TOOL_WRITE_ACTION", "block")

    cfg = get_guardrail_config()

    assert cfg.mode == GuardrailMode.OBSERVE
    assert cfg.context == "planning"
    assert cfg.pii_action == GuardrailAction.REDACT
    assert cfg.prompt_injection_action == GuardrailAction.ISOLATE
    assert cfg.tool_write_action == GuardrailAction.BLOCK


def test_guardrail_config_invalid_env_falls_back(monkeypatch, caplog):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "off")
    monkeypatch.setenv("LARGESTACK_SECRET_ACTION", "permit")

    with caplog.at_level(logging.WARNING):
        cfg = get_guardrail_config()

    assert cfg.mode == GuardrailMode.PROTECT
    assert cfg.secret_action == GuardrailAction.REDACT
    assert "Invalid LARGESTACK_GUARDRAIL_MODE" in caplog.text
    assert "Invalid LARGESTACK_SECRET_ACTION" in caplog.text


def test_guardrail_config_strict_mode(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "strict")

    assert get_guardrail_config().mode == GuardrailMode.STRICT


def test_guardrail_config_warn_mode(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "warn")

    assert get_guardrail_config().mode == GuardrailMode.WARN


def test_guardrail_config_approved_provider_parsing(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_BFSI_APPROVED_PROVIDERS", "deepseek, openai , ,azure")

    cfg = get_guardrail_config()

    assert cfg.bfsi_approved_providers == ("deepseek", "openai", "azure")
