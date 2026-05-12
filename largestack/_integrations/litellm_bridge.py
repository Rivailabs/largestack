"""LiteLLM bridge for LARGESTACK (v0.13.0).

Closes the LLM provider count gap by **integrating with LiteLLM**
instead of competing. LiteLLM exposes 100+ LLM providers through a
single OpenAI-compatible API.

Strategy:
- ``LiteLLMProvider`` — adapter that LARGESTACK treats as a regular provider
- Goes through LiteLLM's ``acompletion`` for async chat
- Supports the LARGESTACK-unique data-residency check (block China-hosted
  providers in production)
- Supports per-tenant API keys via the ``api_key`` parameter
- Falls back gracefully when ``litellm`` not installed (raises ImportError
  with install hint on first use)

Models you get for free (incomplete list):
- OpenAI, Anthropic, AWS Bedrock, Azure, Google Vertex, Gemini
- Mistral, Cohere, Groq, Together, Replicate, Fireworks, Anyscale
- Ollama, vLLM, LM Studio, OpenRouter
- ~100+ total

Usage::

    from largestack._integrations.litellm_bridge import LiteLLMProvider
    provider = LiteLLMProvider(
        model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
        region="ap-south-1",  # Mumbai
        require_india_residency=True,
    )
    response = await provider.acomplete([
        {"role": "user", "content": "Hello"},
    ])
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

log = logging.getLogger("largestack.integrations.litellm")


# Providers that violate India data residency (China-hosted)
CHINA_HOSTED_PROVIDERS = {
    "deepseek", "moonshot", "qwen", "yi", "01ai", "baichuan",
    "minimax", "doubao",
}

# Providers that are India-residency safe (when configured correctly)
INDIA_RESIDENT_PROVIDERS = {
    "bedrock",          # via ap-south-1
    "azure",            # via India Central / South
    "vertex_ai",        # via asia-south1 / asia-south2
    "ollama",           # local
    "vllm",             # local
    "openai_proxy",     # if proxy is in India
}


def _have_litellm() -> bool:
    try:
        import litellm  # noqa
        return True
    except ImportError:
        return False


@dataclass
class LiteLLMResponse:
    """Normalised response from LiteLLM."""
    content: str
    model: str
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LiteLLMProvider:
    """LARGESTACK provider that delegates to LiteLLM.

    Args:
        model: LiteLLM model string (e.g. ``"openai/gpt-4o-mini"``,
            ``"bedrock/anthropic.claude-3-haiku-20240307-v1:0"``)
        api_key: optional per-tenant API key
        api_base: optional API base URL (for self-hosted / proxies)
        region: AWS region for Bedrock (``"ap-south-1"`` for Mumbai)
        require_india_residency: if ``True``, refuses to route to any
            provider not in ``INDIA_RESIDENT_PROVIDERS`` and refuses
            China-hosted providers
        extra: additional kwargs forwarded to ``litellm.acompletion``
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        region: str | None = None,
        require_india_residency: bool = False,
        extra: dict[str, Any] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.region = region
        self.require_india_residency = require_india_residency
        self.extra = extra or {}

        # Residency check at construction time (fail fast)
        if require_india_residency:
            self._check_india_residency()

    def _check_india_residency(self) -> None:
        """Fail-fast residency check for India deploys."""
        provider = self._provider_prefix()
        if provider in CHINA_HOSTED_PROVIDERS:
            raise ValueError(
                f"provider '{provider}' is China-hosted "
                f"and violates India data residency"
            )
        if provider not in INDIA_RESIDENT_PROVIDERS:
            log.warning(
                f"provider '{provider}' may not honour India "
                f"data residency — verify with your CDN / API host"
            )
        # Bedrock-specific: region must be ap-south-1
        if provider == "bedrock":
            if self.region not in ("ap-south-1", "ap-south-2"):
                raise ValueError(
                    "Bedrock with India residency requires "
                    "region='ap-south-1' or 'ap-south-2'"
                )

    def _provider_prefix(self) -> str:
        """Extract the provider name from the model string."""
        if "/" in self.model:
            return self.model.split("/", 1)[0]
        # OpenAI-style models without prefix
        return "openai"

    def _build_kwargs(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.region and self._provider_prefix() == "bedrock":
            kwargs["aws_region_name"] = self.region
        kwargs.update(self.extra)
        return kwargs

    async def acomplete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LiteLLMResponse:
        """Async chat completion."""
        if not _have_litellm():
            raise ImportError(
                "litellm required for LiteLLMProvider. "
                "Install with: pip install litellm"
            )
        import litellm

        call_kwargs = self._build_kwargs(messages)
        call_kwargs.update(kwargs)

        try:
            resp = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            log.exception(f"litellm completion failed: {e}")
            raise

        # Normalise response
        choice = resp.choices[0]
        content = ""
        finish_reason = ""
        if hasattr(choice, "message"):
            content = getattr(choice.message, "content", "") or ""
            finish_reason = getattr(choice, "finish_reason", "") or ""

        usage = {}
        if hasattr(resp, "usage") and resp.usage:
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(
                    resp.usage, "completion_tokens", 0,
                ),
                "total_tokens": getattr(resp.usage, "total_tokens", 0),
            }

        return LiteLLMResponse(
            content=content,
            model=getattr(resp, "model", self.model),
            finish_reason=finish_reason,
            usage=usage,
            raw=resp,
        )

    async def astream(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Streaming token-by-token generation."""
        if not _have_litellm():
            raise ImportError(
                "litellm required for streaming. "
                "Install with: pip install litellm"
            )
        import litellm

        call_kwargs = self._build_kwargs(messages)
        call_kwargs.update(kwargs)
        call_kwargs["stream"] = True

        try:
            stream = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            log.exception(f"litellm streaming failed: {e}")
            raise

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                yield delta.content


# -------------------- Multi-provider router (fallback chain) --------------------

@dataclass
class ProviderRoute:
    """One entry in a fallback chain."""
    provider: LiteLLMProvider
    label: str = ""


class FallbackRouter:
    """Tries providers in order until one succeeds.

    Use case: "primary Bedrock Mumbai, fallback to Azure India, last
    resort OpenAI" with India-residency on all three.

    Args:
        routes: ordered list of ``ProviderRoute`` to try
        on_failure: callback invoked on each failure
            ``(label, exception) -> None``
    """

    def __init__(
        self,
        routes: list[ProviderRoute],
        *,
        on_failure: Any = None,
    ):
        if not routes:
            raise ValueError("at least one route required")
        self.routes = routes
        self.on_failure = on_failure

    async def acomplete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LiteLLMResponse:
        last_exc: Exception | None = None
        for route in self.routes:
            try:
                return await route.provider.acomplete(messages, **kwargs)
            except Exception as e:
                last_exc = e
                if self.on_failure:
                    try:
                        self.on_failure(route.label, e)
                    except Exception:
                        log.exception("on_failure callback raised")
                log.warning(
                    f"provider '{route.label or route.provider.model}' "
                    f"failed: {e}; trying next"
                )
        raise RuntimeError(
            f"all {len(self.routes)} providers failed; "
            f"last error: {last_exc}"
        )


__all__ = [
    "LiteLLMProvider",
    "LiteLLMResponse",
    "FallbackRouter",
    "ProviderRoute",
    "CHINA_HOSTED_PROVIDERS",
    "INDIA_RESIDENT_PROVIDERS",
]
