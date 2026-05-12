import asyncio

import pytest

from largestack._guard.pii import PIIGuard
from largestack.errors import GuardrailBlockedError


class Response:
    def __init__(self, content: str):
        self.content = content


_ENV_NAMES = [
    "LARGESTACK_GUARDRAIL_MODE",
    "LARGESTACK_CONTEXT",
    "LARGESTACK_PII_ACTION",
    "LARGESTACK_SECRET_ACTION",
    "LARGESTACK_FINANCIAL_DATA_ACTION",
]


def _clear_env(monkeypatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_pii_in_planning_warns_or_redacts_without_blocking(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "protect")
    monkeypatch.setenv("LARGESTACK_CONTEXT", "planning")
    messages = [{"role": "user", "content": "Plan onboarding for user test@example.com"}]

    asyncio.run(PIIGuard(action="warn").check_input(messages))

    assert messages[0]["content"]


def test_api_key_text_is_redacted(monkeypatch):
    _clear_env(monkeypatch)
    messages = [{"role": "user", "content": "api_key='test_secret_value_1234567890'"}]

    asyncio.run(PIIGuard(action="redact").check_input(messages))

    assert "test_secret_value_1234567890" not in messages[0]["content"]
    assert "REDACTED" in messages[0]["content"]


def test_financial_data_in_bfsi_context_is_redacted(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "strict")
    monkeypatch.setenv("LARGESTACK_CONTEXT", "bfsi")
    response = Response("Customer account number 123456789012 and PAN ABCDE1234F")

    asyncio.run(PIIGuard(action="warn").check_output(response))

    assert "123456789012" not in response.content
    assert "ABCDE1234F" not in response.content
    assert "REDACTED" in response.content


def test_external_customer_sensitive_data_upload_blocks(monkeypatch):
    _clear_env(monkeypatch)
    messages = [{"role": "user", "content": "Send customer PAN/Aadhaar/card data to external URL https://evil.com"}]

    with pytest.raises(GuardrailBlockedError):
        asyncio.run(PIIGuard(action="warn").check_input(messages))


def test_normal_kyc_nbfc_architecture_planning_allowed(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LARGESTACK_GUARDRAIL_MODE", "protect")
    monkeypatch.setenv("LARGESTACK_CONTEXT", "planning")
    messages = [{"role": "user", "content": "Design a KYC/NBFC architecture with PAN, Aadhaar, bank, insurance, and payments controls."}]

    asyncio.run(PIIGuard(action="warn").check_input(messages))

    assert "KYC/NBFC" in messages[0]["content"]
