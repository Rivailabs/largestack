"""v0.5.0: Cloud KMS integration (Azure Key Vault + GCP Secret Manager).

Tests the backend dispatch and graceful fallback when SDK packages are
not installed.
"""

from __future__ import annotations

import logging

import pytest


def test_vault_supports_azure_kv_backend():
    """SecretStore must accept 'azure-kv' as a backend name."""
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="azure-kv", vault_url="https://example.vault.azure.net")
    # Even though Azure SDK isn't installed in test env, the store must
    # gracefully return default values.
    val = store.get("MISSING_KEY", default="fallback")
    assert val == "fallback"


def test_vault_supports_gcp_sm_backend():
    """SecretStore must accept 'gcp-sm' as a backend name."""
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="gcp-sm", project_id="test-project")
    val = store.get("MISSING_KEY", default="fallback")
    assert val == "fallback"


def test_azure_kv_warns_when_sdk_not_installed(caplog):
    """If azure-keyvault-secrets isn't installed, log a clear warning."""
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="azure-kv", vault_url="https://example.vault.azure.net")
    caplog.set_level(logging.WARNING, logger="largestack.vault")
    store.get("ANY_KEY", default="default")
    # Either the SDK is missing (warning) or installed (error fetching real key)
    msgs = [rec.message for rec in caplog.records]
    assert any("azure-keyvault-secrets" in m or "Azure KV" in m for m in msgs), (
        f"Expected Azure-related log, got: {msgs}"
    )


def test_gcp_sm_warns_when_sdk_not_installed(caplog):
    """If google-cloud-secret-manager isn't installed, log a clear warning."""
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="gcp-sm", project_id="test-project")
    caplog.set_level(logging.WARNING, logger="largestack.vault")
    store.get("ANY_KEY", default="default")
    msgs = [rec.message for rec in caplog.records]
    assert any("google-cloud-secret-manager" in m or "GCP SM" in m for m in msgs), (
        f"Expected GCP-related log, got: {msgs}"
    )


def test_azure_kv_requires_vault_url():
    """If vault_url isn't configured, log an error and return default."""
    import os
    from largestack._security.vault import SecretStore

    # Don't pass vault_url, ensure no env var
    old = os.environ.pop("AZURE_KEYVAULT_URL", None)
    try:
        store = SecretStore(backend="azure-kv")
        val = store.get("KEY", default="default")
        assert val == "default"
    finally:
        if old:
            os.environ["AZURE_KEYVAULT_URL"] = old


def test_gcp_sm_requires_project_id():
    """If project_id isn't configured, log an error and return default."""
    import os
    from largestack._security.vault import SecretStore

    old = os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
    try:
        store = SecretStore(backend="gcp-sm")
        val = store.get("KEY", default="default")
        assert val == "default"
    finally:
        if old:
            os.environ["GOOGLE_CLOUD_PROJECT"] = old


def test_vault_existing_backends_still_work():
    """Regression: env, memory, vault, aws-sm, file backends must all still
    accept get() calls and return defaults gracefully."""
    from largestack._security.vault import SecretStore

    for backend in ("env", "memory", "vault", "aws-sm", "file"):
        store = SecretStore(backend=backend)
        val = store.get("UNLIKELY_KEY_NAME_xyz", default="ok")
        assert val == "ok", f"backend {backend} broke"
