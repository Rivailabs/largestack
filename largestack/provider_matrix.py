"""Provider capability matrix for LARGESTACK.

This module makes provider support explicit so users do not confuse an adapter
existing in source code with fully verified production support. Use it in docs,
CLIs, dashboards, and tests to show what is supported, partial, or unverified.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Literal

SupportStatus = Literal["verified", "partial", "experimental", "adapter_only"]

@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    chat: bool
    streaming: bool
    tool_calling: bool
    structured_output: bool
    cost_tracking: bool
    local: bool = False
    status: SupportStatus = "partial"
    notes: str = ""

PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability("openai", True, True, True, True, True, status="verified", notes="Primary OpenAI chat/tool path."),
    ProviderCapability("deepseek", True, True, True, True, True, status="verified", notes="OpenAI-compatible provider path; function calling supported by DeepSeek models that expose it."),
    ProviderCapability("anthropic", True, True, True, True, True, status="verified", notes="Native Anthropic tool mapping."),
    ProviderCapability("litellm", True, True, True, True, True, status="partial", notes="Gateway to many providers; exact capabilities depend on downstream provider/model."),
    ProviderCapability("local", True, True, True, True, False, local=True, status="partial", notes="Generic OpenAI-compatible local endpoint using LARGESTACK_OPENAI_COMPATIBLE_BASE_URL or Ollama /v1 compat mode."),
    ProviderCapability("ollama", True, True, False, False, False, local=True, status="partial", notes="Native Ollama chat path. Use local/ or ollama_openai/ for OpenAI-compatible tool attempts."),
    ProviderCapability("ollama_openai", True, True, True, True, False, local=True, status="experimental", notes="Ollama OpenAI-compatible /v1 endpoint. Tool success depends on model/runtime support."),
    ProviderCapability("google", True, True, False, False, True, status="partial", notes="Chat path present; tool path not first-class."),
    ProviderCapability("groq", True, True, True, True, True, status="partial", notes="OpenAI-compatible provider; verify model-specific tool support."),
    ProviderCapability("mistral", True, True, True, True, True, status="partial", notes="Verify model-specific tool support."),
    ProviderCapability("cohere", True, False, False, False, True, status="partial", notes="Chat path present; full tool parsing not guaranteed."),
    ProviderCapability("bedrock", True, False, False, False, True, status="partial", notes="Requires AWS credentials and provider-specific validation."),
    ProviderCapability("azure", True, True, True, True, True, status="partial", notes="Azure OpenAI-compatible path."),
    ProviderCapability("openrouter", True, True, True, True, True, status="partial", notes="OpenAI-compatible aggregator; capabilities vary per routed model."),
    ProviderCapability("perplexity", True, True, False, False, True, status="partial", notes="Chat/research models; tool support varies."),
    ProviderCapability("cerebras", True, True, True, True, True, status="partial", notes="OpenAI-compatible path; verify live."),
    ProviderCapability("sambanova", True, True, True, True, True, status="partial", notes="OpenAI-compatible path; verify live."),
    ProviderCapability("xai", True, True, True, True, True, status="partial", notes="OpenAI-compatible path; verify live."),
    ProviderCapability("ai21", True, False, False, False, True, status="partial", notes="Provider adapter present; verify live."),
    ProviderCapability("lepton", True, True, True, True, True, status="partial", notes="OpenAI-compatible path; verify live."),
    ProviderCapability("nvidia", True, True, True, True, True, status="partial", notes="OpenAI-compatible path; verify live."),
    ProviderCapability("anyscale", True, True, True, True, True, status="adapter_only", notes="Adapter exists; wire/verify before public claim."),
    ProviderCapability("cloudflare", True, False, False, False, True, status="adapter_only", notes="Adapter exists; wire/verify before public claim."),
    ProviderCapability("databricks", True, True, True, True, True, status="adapter_only", notes="Adapter exists; wire/verify before public claim."),
    ProviderCapability("replicate", True, False, False, False, True, status="adapter_only", notes="Adapter exists; wire/verify before public claim."),
    ProviderCapability("voyage", False, False, False, False, True, status="adapter_only", notes="Embeddings-oriented provider; not chat-agent path."),
)


def provider_support_matrix() -> list[dict]:
    """Return provider support as JSON-serializable dictionaries."""
    return [asdict(p) for p in PROVIDER_CAPABILITIES]


def get_provider_capabilities(provider: str) -> dict:
    """Return one provider capability record.

    Raises:
        KeyError: if provider is unknown.
    """
    normalized = provider.lower().replace("-", "_")
    for p in PROVIDER_CAPABILITIES:
        if p.provider == normalized:
            return asdict(p)
    raise KeyError(f"Unknown provider: {provider}")


def tool_capable_providers(*, include_partial: bool = True) -> list[str]:
    """Return provider names that can support tool calling."""
    return [p.provider for p in PROVIDER_CAPABILITIES if p.tool_calling and (include_partial or p.status == "verified")]


__all__ = [
    "ProviderCapability", "PROVIDER_CAPABILITIES", "provider_support_matrix",
    "get_provider_capabilities", "tool_capable_providers",
]
