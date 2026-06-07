"""v0.14.0: Tests for Langfuse adapter."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# -------------------- LangfuseConfig --------------------


def test_config_reads_env_vars(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-from-env")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-from-env")
    monkeypatch.setenv("LANGFUSE_HOST", "https://lf.example.in")

    from largestack._integrations.langfuse_adapter import LangfuseConfig

    cfg = LangfuseConfig()
    assert cfg.public_key == "pk-from-env"
    assert cfg.secret_key == "sk-from-env"
    assert cfg.host == "https://lf.example.in"


def test_config_explicit_overrides():
    from largestack._integrations.langfuse_adapter import LangfuseConfig

    cfg = LangfuseConfig(
        public_key="pk-explicit",
        secret_key="sk-explicit",
        host="https://my.host",
    )
    assert cfg.public_key == "pk-explicit"
    assert cfg.host == "https://my.host"


def test_config_india_residency_blocks_eu_cloud():
    from largestack._integrations.langfuse_adapter import LangfuseConfig

    with pytest.raises(ValueError, match="India-resident"):
        LangfuseConfig(
            public_key="pk",
            secret_key="sk",
            host="https://cloud.langfuse.com",
            allow_non_india_host=False,
        )


def test_config_india_residency_allows_mumbai():
    from largestack._integrations.langfuse_adapter import LangfuseConfig

    cfg = LangfuseConfig(
        public_key="pk",
        secret_key="sk",
        host="https://langfuse.ap-south-1.aws.example",
        allow_non_india_host=False,
    )
    assert "ap-south" in cfg.host


def test_config_india_residency_allows_in_tld():
    from largestack._integrations.langfuse_adapter import LangfuseConfig

    cfg = LangfuseConfig(
        public_key="pk",
        secret_key="sk",
        host="https://lf.rivailabs.in",
        allow_non_india_host=False,
    )
    assert cfg.host.endswith(".in")


# -------------------- configure_langfuse --------------------


def test_configure_requires_public_key():
    from largestack._integrations.langfuse_adapter import (
        configure_langfuse,
        LangfuseConfig,
    )

    cfg = LangfuseConfig(public_key="", secret_key="sk")
    with pytest.raises(ValueError, match="public_key"):
        configure_langfuse(cfg)


def test_configure_requires_secret_key():
    from largestack._integrations.langfuse_adapter import (
        configure_langfuse,
        LangfuseConfig,
    )

    cfg = LangfuseConfig(public_key="pk", secret_key="")
    with pytest.raises(ValueError, match="secret_key"):
        configure_langfuse(cfg)


def test_configure_returns_tracer():
    from largestack._integrations.langfuse_adapter import (
        configure_langfuse,
        LangfuseConfig,
        LangfuseTracer,
    )

    tracer = configure_langfuse(
        LangfuseConfig(
            public_key="pk-test",
            secret_key="sk-test",
        )
    )
    assert isinstance(tracer, LangfuseTracer)


def test_get_tracer_returns_configured():
    from largestack._integrations.langfuse_adapter import (
        configure_langfuse,
        LangfuseConfig,
        get_tracer,
    )

    tracer = configure_langfuse(
        LangfuseConfig(
            public_key="pk-x",
            secret_key="sk-x",
        )
    )
    assert get_tracer() is tracer


# -------------------- LangfuseTracer (mocked) --------------------


def test_tracer_get_client_raises_without_langfuse():
    from largestack._integrations import langfuse_adapter
    from largestack._integrations.langfuse_adapter import (
        LangfuseTracer,
        LangfuseConfig,
    )

    with patch.object(langfuse_adapter, "_have_langfuse", return_value=False):
        t = LangfuseTracer(
            LangfuseConfig(
                public_key="pk",
                secret_key="sk",
            )
        )
        with pytest.raises(ImportError, match="langfuse"):
            t.get_client()


# -------------------- Attribute builders --------------------


def test_langfuse_attributes_for_dpdp():
    from largestack._integrations.langfuse_adapter import (
        langfuse_attributes_for_dpdp,
    )

    attrs = langfuse_attributes_for_dpdp(
        section="Section 6",
        purpose="KYC verification",
        lawful_basis="consent",
    )
    assert attrs["compliance.dpdp.section"] == "Section 6"
    assert attrs["compliance.dpdp.purpose"] == "KYC verification"
    assert attrs["compliance.framework"] == "DPDP_Act_2023"


def test_langfuse_attributes_for_rbi():
    from largestack._integrations.langfuse_adapter import (
        langfuse_attributes_for_rbi,
    )

    attrs = langfuse_attributes_for_rbi(framework="MD-NBFC-D")
    assert attrs["compliance.rbi.framework"] == "MD-NBFC-D"


def test_langfuse_attributes_for_tenant_requires_id():
    from largestack._integrations.langfuse_adapter import (
        langfuse_attributes_for_tenant,
    )

    with pytest.raises(ValueError, match="tenant_id"):
        langfuse_attributes_for_tenant(tenant_id="")


def test_langfuse_attributes_for_tenant_includes_sector():
    from largestack._integrations.langfuse_adapter import (
        langfuse_attributes_for_tenant,
    )

    attrs = langfuse_attributes_for_tenant(
        tenant_id="nbfc-001",
        sector="financial",
    )
    assert attrs["tenant.id"] == "nbfc-001"
    assert attrs["tenant.sector"] == "financial"
