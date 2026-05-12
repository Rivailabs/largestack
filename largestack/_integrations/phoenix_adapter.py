"""Arize Phoenix adapter (v0.14.0).

Closes Tier D #44. Phoenix is the OpenInference-native observability
platform from Arize — drift detection + tracing + evaluation.

Strategy: pair, don't replace. LARGESTACK exports OTEL → Phoenix renders.
This module makes the pairing zero-config and adds OpenInference
semantic conventions for LARGESTACK-specific spans.

Phoenix spans use OpenInference conventions:
- ``llm.input_messages`` / ``llm.output_messages``
- ``llm.token_count.prompt`` / ``llm.token_count.completion``
- ``retrieval.documents``
- ``embedding.embeddings``

LARGESTACK-unique extensions:
- ``compliance.framework`` — DPDP / RBI / PMLA tag
- ``tenant.id`` — multi-tenant isolation indicator
- ``indic.script`` — Devanagari / Bengali / etc.

Usage::

    from largestack._integrations.phoenix_adapter import (
        PhoenixConfig, configure_phoenix,
    )

    configure_phoenix(PhoenixConfig(
        endpoint="http://localhost:6006",  # local dev
        # or hosted: endpoint="https://app.phoenix.arize.com"
        project_name="my-kyc-pipeline",
    ))

    # LARGESTACK spans now flow to Phoenix automatically
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("largestack.integrations.phoenix")


@dataclass
class PhoenixConfig:
    """Phoenix client configuration.

    Either pass values explicitly or set environment:
    - ``PHOENIX_ENDPOINT`` (default ``http://localhost:6006``)
    - ``PHOENIX_API_KEY`` (for hosted Phoenix Cloud)
    - ``PHOENIX_PROJECT_NAME``
    """
    endpoint: str = "http://localhost:6006"
    api_key: str = ""
    project_name: str = "default"
    enable: bool = True
    # Phoenix is self-hostable, so India residency is achievable when
    # self-hosted in Mumbai. Hosted Phoenix Cloud is US-based.
    allow_non_india_host: bool = True

    def __post_init__(self):
        if self.endpoint == "http://localhost:6006":
            env_endpoint = os.getenv("PHOENIX_ENDPOINT")
            if env_endpoint:
                self.endpoint = env_endpoint
        if not self.api_key:
            self.api_key = os.getenv("PHOENIX_API_KEY", "")
        if self.project_name == "default":
            env_project = os.getenv("PHOENIX_PROJECT_NAME")
            if env_project:
                self.project_name = env_project

        if not self.allow_non_india_host:
            india_markers = (
                "ap-south", "mumbai", ".in/", ".in:", ".in",
                "localhost", "127.0.0.1",  # local self-host is fine
            )
            ep = self.endpoint.lower()
            if not any(m in ep for m in india_markers):
                raise ValueError(
                    f"endpoint '{self.endpoint}' may not be "
                    "India-resident. Set allow_non_india_host=True or "
                    "self-host in Mumbai."
                )


def _have_phoenix() -> bool:
    try:
        import phoenix  # noqa
        return True
    except ImportError:
        return False


def _have_openinference() -> bool:
    try:
        import openinference  # noqa
        return True
    except ImportError:
        return False


# -------------------- Configuration --------------------

class PhoenixIntegration:
    """Phoenix integration handle."""

    def __init__(self, config: PhoenixConfig):
        self.config = config
        self._tracer_provider = None

    def setup_otel(self) -> bool:
        """Configure OTEL to export to Phoenix's OTLP endpoint.

        Returns True on success.
        """
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
            except ImportError:
                log.warning(
                    "opentelemetry-exporter-otlp-proto-http required. "
                    "Install: pip install opentelemetry-exporter-otlp"
                )
                return False
        except ImportError as e:
            log.warning(f"OTEL setup failed: {e}")
            return False

        endpoint = (
            f"{self.config.endpoint.rstrip('/')}/v1/traces"
        )
        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["api_key"] = self.config.api_key

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        resource = Resource.create({
            "service.name": self.config.project_name,
            "openinference.project.name": self.config.project_name,
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._tracer_provider = provider
        log.info(
            f"Phoenix OTEL configured: {endpoint} "
            f"(project: {self.config.project_name})"
        )
        return True

    def shutdown(self) -> None:
        """Flush + shut down the tracer provider."""
        if self._tracer_provider is not None:
            try:
                self._tracer_provider.shutdown()
            except Exception as e:
                log.warning(f"phoenix shutdown failed: {e}")


_global_integration: PhoenixIntegration | None = None


def configure_phoenix(config: PhoenixConfig) -> PhoenixIntegration:
    """Configure global Phoenix integration."""
    global _global_integration
    integration = PhoenixIntegration(config)
    integration.setup_otel()
    _global_integration = integration
    return integration


def get_integration() -> PhoenixIntegration | None:
    return _global_integration


# -------------------- OpenInference semantic conventions --------------------

# Standard OpenInference attribute names (subset)
class OISpanKind:
    LLM = "LLM"
    CHAIN = "CHAIN"
    RETRIEVER = "RETRIEVER"
    EMBEDDING = "EMBEDDING"
    AGENT = "AGENT"
    TOOL = "TOOL"
    GUARDRAIL = "GUARDRAIL"
    EVALUATOR = "EVALUATOR"


def openinference_attributes_for_llm(
    *,
    model: str,
    input_messages: list[dict[str, Any]],
    output_messages: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> dict[str, Any]:
    """Build OpenInference attributes for an LLM call span."""
    import json
    attrs: dict[str, Any] = {
        "openinference.span.kind": OISpanKind.LLM,
        "llm.model_name": model,
        "llm.input_messages": json.dumps(input_messages),
    }
    if output_messages is not None:
        attrs["llm.output_messages"] = json.dumps(output_messages)
    if prompt_tokens:
        attrs["llm.token_count.prompt"] = prompt_tokens
    if completion_tokens:
        attrs["llm.token_count.completion"] = completion_tokens
    if total_tokens:
        attrs["llm.token_count.total"] = total_tokens
    return attrs


def openinference_attributes_for_retrieval(
    *,
    query: str,
    documents: list[dict[str, Any]],
    retriever_name: str = "",
) -> dict[str, Any]:
    """Build OpenInference attributes for a retrieval span."""
    import json
    return {
        "openinference.span.kind": OISpanKind.RETRIEVER,
        "input.value": query,
        "retrieval.documents": json.dumps(documents),
        "retrieval.documents.count": len(documents),
        "retriever.name": retriever_name,
    }


def openinference_attributes_for_embedding(
    *,
    model: str,
    text_count: int,
    dimension: int = 0,
) -> dict[str, Any]:
    """Build OpenInference attributes for an embedding span."""
    return {
        "openinference.span.kind": OISpanKind.EMBEDDING,
        "embedding.model_name": model,
        "embedding.embeddings.count": text_count,
        "embedding.dimension": dimension,
    }


def openinference_attributes_for_tool(
    *,
    tool_name: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build OpenInference attributes for a tool span."""
    import json
    attrs: dict[str, Any] = {
        "openinference.span.kind": OISpanKind.TOOL,
        "tool.name": tool_name,
    }
    if parameters is not None:
        attrs["tool.parameters"] = json.dumps(parameters, default=str)
    return attrs


# -------------------- LARGESTACK-unique extensions --------------------

def phoenix_attributes_for_compliance(
    *,
    framework: Literal["DPDP_Act_2023", "RBI", "PMLA", "IT_Act"],
    section: str = "",
    tenant_id: str = "",
) -> dict[str, str]:
    """LARGESTACK-unique compliance attributes for Phoenix filtering."""
    attrs: dict[str, str] = {
        "compliance.framework": framework,
    }
    if section:
        attrs["compliance.section"] = section
    if tenant_id:
        attrs["tenant.id"] = tenant_id
    return attrs


def phoenix_attributes_for_indic(
    *,
    script: Literal[
        "devanagari", "bengali", "tamil", "telugu", "kannada",
        "malayalam", "gujarati", "punjabi", "odia",
    ],
    language: str = "",
) -> dict[str, str]:
    """LARGESTACK-unique Indic-script attributes."""
    attrs: dict[str, str] = {"indic.script": script}
    if language:
        attrs["indic.language"] = language
    return attrs


__all__ = [
    "PhoenixConfig",
    "PhoenixIntegration",
    "configure_phoenix",
    "get_integration",
    "OISpanKind",
    "openinference_attributes_for_llm",
    "openinference_attributes_for_retrieval",
    "openinference_attributes_for_embedding",
    "openinference_attributes_for_tool",
    "phoenix_attributes_for_compliance",
    "phoenix_attributes_for_indic",
]
