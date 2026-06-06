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
    ProviderCapability("anthropic", True, True, True, True, True, status="adapter_only", notes="Native Anthropic adapter (messages API, tool input_schema mapping, prompt caching). Structurally complete but NOT live-verified end-to-end (no key tested) — run check_connection() with your key."),
    ProviderCapability("litellm", True, True, True, True, True, status="partial", notes="Gateway to many providers; exact capabilities depend on downstream provider/model."),
    ProviderCapability("local", True, True, True, True, False, local=True, status="partial", notes="Generic OpenAI-compatible local endpoint using LARGESTACK_OPENAI_COMPATIBLE_BASE_URL or Ollama /v1 compat mode."),
    ProviderCapability("ollama", True, True, False, False, False, local=True, status="verified", notes="Native Ollama /api/chat. Live-verified on qwen2.5:0.5b (chat round-trip, cost=0). Tools go via ollama_openai/."),
    ProviderCapability("ollama_openai", True, True, True, True, False, local=True, status="verified", notes="Ollama OpenAI-compatible /v1. Live-verified on qwen2.5:0.5b: chat + function-calling (tool round-trip). Tool reliability still depends on the local model."),
    ProviderCapability("google", True, True, True, True, True, status="verified", notes="Live-verified on gemini-2.5-flash: chat, function-calling (tools), structured output, cost."),
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


async def check_connection(model: str, timeout: int = 30) -> dict:
    """Live connectivity self-test: make a minimal real call to the provider behind
    ``model`` and report whether the API connection works. Needs the provider's API
    key in the environment. Returns: ``{provider, model, ok, detail, cost}``.

    This is the honest way to verify a provider — "the adapter shares DeepSeek's code"
    is not the same as "your key + endpoint answer." Run it once per provider/key.

    Example::

        import asyncio
        from largestack import check_connection
        print(asyncio.run(check_connection("groq/llama-3.3-70b-versatile")))
    """
    from largestack import Agent

    provider = model.split("/")[0] if "/" in model else model
    try:
        agent = Agent(name="conncheck", llm=model, guardrails=None, max_turns=1, cost_budget=0.05)
        try:
            result = await agent.run("Reply with the single word: ok", timeout=timeout)
        finally:
            try:
                await agent.aclose()
            except Exception:
                pass
        return {"provider": provider, "model": model, "ok": bool(getattr(result, "content", None)),
                "detail": (result.content or "")[:80],
                "cost": float(getattr(result, "total_cost", 0.0) or 0.0)}
    except Exception as exc:  # noqa: BLE001 — a connectivity probe reports the error as data
        return {"provider": provider, "model": model, "ok": False,
                "detail": f"{type(exc).__name__}: {exc}"[:160], "cost": 0.0}


__all__ = [
    "ProviderCapability", "PROVIDER_CAPABILITIES", "provider_support_matrix",
    "get_provider_capabilities", "tool_capable_providers", "check_connection",
]
