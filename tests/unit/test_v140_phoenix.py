"""v0.14.0: Tests for Arize Phoenix adapter."""

from __future__ import annotations

import json

import pytest


# -------------------- PhoenixConfig --------------------


def test_config_defaults_to_localhost():
    from largestack._integrations.phoenix_adapter import PhoenixConfig

    cfg = PhoenixConfig()
    assert cfg.endpoint == "http://localhost:6006"
    assert cfg.project_name == "default"


def test_config_reads_env_vars(monkeypatch):
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://my-phoenix:6006")
    monkeypatch.setenv("PHOENIX_API_KEY", "ax-test")
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "kyc-prod")

    from largestack._integrations.phoenix_adapter import PhoenixConfig

    cfg = PhoenixConfig()
    assert cfg.endpoint == "http://my-phoenix:6006"
    assert cfg.api_key == "ax-test"
    assert cfg.project_name == "kyc-prod"


def test_config_localhost_passes_india_residency():
    from largestack._integrations.phoenix_adapter import PhoenixConfig

    cfg = PhoenixConfig(
        endpoint="http://localhost:6006",
        allow_non_india_host=False,
    )
    assert cfg.endpoint == "http://localhost:6006"


def test_config_arize_cloud_blocked_with_strict_residency():
    from largestack._integrations.phoenix_adapter import PhoenixConfig

    with pytest.raises(ValueError, match="India-resident"):
        PhoenixConfig(
            endpoint="https://app.phoenix.arize.com",
            allow_non_india_host=False,
        )


# -------------------- configure_phoenix --------------------


def test_configure_returns_integration():
    from largestack._integrations.phoenix_adapter import (
        configure_phoenix,
        PhoenixConfig,
        PhoenixIntegration,
    )

    integration = configure_phoenix(
        PhoenixConfig(
            endpoint="http://localhost:6006",
            project_name="test",
        )
    )
    assert isinstance(integration, PhoenixIntegration)


def test_get_integration_returns_configured():
    from largestack._integrations.phoenix_adapter import (
        configure_phoenix,
        PhoenixConfig,
        get_integration,
    )

    integration = configure_phoenix(
        PhoenixConfig(
            endpoint="http://localhost:6006",
        )
    )
    assert get_integration() is integration


# -------------------- OpenInference attributes --------------------


def test_oi_attrs_for_llm_includes_kind():
    from largestack._integrations.phoenix_adapter import (
        openinference_attributes_for_llm,
        OISpanKind,
    )

    attrs = openinference_attributes_for_llm(
        model="bedrock/claude-3-haiku",
        input_messages=[{"role": "user", "content": "hi"}],
        output_messages=[{"role": "assistant", "content": "hello"}],
        prompt_tokens=5,
        completion_tokens=2,
    )
    assert attrs["openinference.span.kind"] == OISpanKind.LLM
    assert attrs["llm.model_name"] == "bedrock/claude-3-haiku"
    assert attrs["llm.token_count.prompt"] == 5
    assert attrs["llm.token_count.completion"] == 2


def test_oi_attrs_for_llm_serializes_messages_as_json():
    from largestack._integrations.phoenix_adapter import (
        openinference_attributes_for_llm,
    )

    attrs = openinference_attributes_for_llm(
        model="x",
        input_messages=[{"role": "user", "content": "hi"}],
    )
    # input_messages must be JSON-encoded for OTEL string attributes
    parsed = json.loads(attrs["llm.input_messages"])
    assert parsed[0]["role"] == "user"


def test_oi_attrs_for_retrieval():
    from largestack._integrations.phoenix_adapter import (
        openinference_attributes_for_retrieval,
        OISpanKind,
    )

    docs = [
        {"id": "d1", "content": "doc1"},
        {"id": "d2", "content": "doc2"},
    ]
    attrs = openinference_attributes_for_retrieval(
        query="loan history",
        documents=docs,
        retriever_name="qdrant",
    )
    assert attrs["openinference.span.kind"] == OISpanKind.RETRIEVER
    assert attrs["retrieval.documents.count"] == 2
    assert attrs["retriever.name"] == "qdrant"


def test_oi_attrs_for_embedding():
    from largestack._integrations.phoenix_adapter import (
        openinference_attributes_for_embedding,
    )

    attrs = openinference_attributes_for_embedding(
        model="text-embedding-3-small",
        text_count=5,
        dimension=1536,
    )
    assert attrs["embedding.model_name"] == "text-embedding-3-small"
    assert attrs["embedding.embeddings.count"] == 5
    assert attrs["embedding.dimension"] == 1536


def test_oi_attrs_for_tool():
    from largestack._integrations.phoenix_adapter import (
        openinference_attributes_for_tool,
        OISpanKind,
    )

    attrs = openinference_attributes_for_tool(
        tool_name="aadhaar_verify",
        parameters={"aadhaar_last4": "9012"},
    )
    assert attrs["openinference.span.kind"] == OISpanKind.TOOL
    assert attrs["tool.name"] == "aadhaar_verify"


# -------------------- LARGESTACK-unique extensions --------------------


def test_phoenix_attrs_for_compliance_dpdp():
    from largestack._integrations.phoenix_adapter import (
        phoenix_attributes_for_compliance,
    )

    attrs = phoenix_attributes_for_compliance(
        framework="DPDP_Act_2023",
        section="Section 6",
        tenant_id="nbfc-001",
    )
    assert attrs["compliance.framework"] == "DPDP_Act_2023"
    assert attrs["compliance.section"] == "Section 6"
    assert attrs["tenant.id"] == "nbfc-001"


def test_phoenix_attrs_for_indic_devanagari():
    from largestack._integrations.phoenix_adapter import (
        phoenix_attributes_for_indic,
    )

    attrs = phoenix_attributes_for_indic(
        script="devanagari",
        language="hi",
    )
    assert attrs["indic.script"] == "devanagari"
    assert attrs["indic.language"] == "hi"


def test_phoenix_integration_setup_otel_returns_bool():
    """Phoenix setup_otel returns False if OTEL deps missing."""
    from largestack._integrations.phoenix_adapter import (
        PhoenixIntegration,
        PhoenixConfig,
    )

    integration = PhoenixIntegration(
        PhoenixConfig(
            endpoint="http://localhost:6006",
        )
    )
    # Either succeeds (OTEL installed) or returns False
    result = integration.setup_otel()
    assert isinstance(result, bool)


def test_phoenix_integration_shutdown_safe_when_unset():
    """Calling shutdown without prior setup must not raise."""
    from largestack._integrations.phoenix_adapter import (
        PhoenixIntegration,
        PhoenixConfig,
    )

    integration = PhoenixIntegration(
        PhoenixConfig(
            endpoint="http://localhost:6006",
        )
    )
    # shutdown without setup_otel — must not raise
    integration.shutdown()
