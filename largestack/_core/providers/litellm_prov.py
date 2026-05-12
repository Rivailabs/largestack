"""LiteLLM provider — gateway to 100+ LLM providers (v0.7.0).

LiteLLM (https://github.com/BerriAI/litellm) gives a single, unified
interface to call 100+ LLM providers in OpenAI format. By wrapping it
as a LARGESTACK provider, every LiteLLM-supported model becomes a LARGESTACK
model — Bedrock, Vertex, Cohere, Mistral, Together, Groq, Fireworks,
Perplexity, Anyscale, Replicate, HuggingFace, OpenRouter, Cerebras,
DeepInfra, OctoAI, Yi, Moonshot, Zhipu, and ~80 more.

Usage:
    from largestack import Agent

    # Bedrock Claude
    agent = Agent(name="bk", llm="litellm/bedrock/anthropic.claude-3-sonnet-20240229-v1:0")

    # Vertex Gemini
    agent = Agent(name="vx", llm="litellm/vertex_ai/gemini-1.5-pro")

    # Cohere Command
    agent = Agent(name="co", llm="litellm/cohere/command-r-plus")

    # Together
    agent = Agent(name="tg", llm="litellm/together_ai/meta-llama/Llama-3-70b-chat-hf")

The model string format is ``litellm/<provider>/<model>`` — the part
after ``litellm/`` is passed verbatim to LiteLLM.

Authentication: each provider's environment variables (e.g. AWS creds for
Bedrock, GOOGLE_APPLICATION_CREDENTIALS for Vertex, COHERE_API_KEY for
Cohere) work normally — LiteLLM reads them itself.

Requires: ``pip install litellm``. Without it, this provider raises a
clear ImportError on first use.
"""
from __future__ import annotations
import json
import logging
from typing import Any, AsyncIterator

from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderRateLimitError, ProviderError, ProviderTimeoutError
from largestack.types import LLMResponse, ToolCall

log = logging.getLogger("largestack.providers.litellm")


class LiteLLMProvider(BaseProvider):
    """Wraps LiteLLM as a LARGESTACK provider for access to 100+ models.

    Lazy-imports LiteLLM only when ``chat()`` or ``chat_stream()`` is
    called — keeps LARGESTACK startup time fast even when LiteLLM isn't used.
    """
    name = "litellm"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        # api_key + base_url are passed through to LiteLLM if set,
        # but LiteLLM also reads from env vars per provider — so they're
        # genuinely optional.
        self._api_key = api_key
        self._base_url = base_url
        self._litellm = None

    def _lazy_import(self):
        """Import LiteLLM on first use. Raises clear error if missing."""
        if self._litellm is None:
            try:
                import litellm  # type: ignore
                # Suppress LiteLLM's verbose info logs by default
                litellm.suppress_debug_info = True
                self._litellm = litellm
            except ImportError as e:
                raise ImportError(
                    "litellm not installed. Run: pip install litellm"
                ) from e
        return self._litellm

    def get_model(self, model: str) -> str:
        """``litellm/bedrock/anthropic.claude-3-sonnet`` -> 
        ``bedrock/anthropic.claude-3-sonnet``.
        
        Strips only the ``litellm/`` prefix, leaving the provider/model
        intact for LiteLLM to dispatch.
        """
        return model.split("/", 1)[1] if "/" in model else model

    def _map_exception(self, exc: Exception) -> Exception:
        """Translate LiteLLM exceptions to LARGESTACK exception types."""
        msg = str(exc).lower()
        ll = self._litellm
        if ll:
            try:
                if isinstance(exc, ll.AuthenticationError):
                    return ProviderAuthError(self.name, str(exc))
                if isinstance(exc, ll.RateLimitError):
                    return ProviderRateLimitError(self.name, str(exc))
                if isinstance(exc, ll.Timeout):
                    return ProviderTimeoutError(self.name, str(exc))
            except AttributeError:
                pass
        # Fallback by message inspection
        if "auth" in msg or "api key" in msg or "401" in msg:
            return ProviderAuthError(self.name, str(exc))
        if "rate" in msg or "429" in msg or "quota" in msg:
            return ProviderRateLimitError(self.name, str(exc))
        if "timeout" in msg or "timed out" in msg:
            return ProviderTimeoutError(self.name, str(exc))
        return ProviderError(self.name, str(exc))

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kw,
    ) -> LLMResponse:
        litellm = self._lazy_import()
        mn = self.get_model(model)

        body: dict[str, Any] = {
            "model": mn,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            # LiteLLM accepts OpenAI tool format directly
            body["tools"] = [{"type": "function", "function": t} for t in tools]

        # Forward common behavior kwargs that LiteLLM understands
        for k in ("response_format", "tool_choice", "seed", "top_p", "stop", "stop_sequences"):
            if k in kw:
                body[k] = kw[k]
        if self._api_key:
            body["api_key"] = self._api_key
        if self._base_url:
            body["api_base"] = self._base_url

        try:
            resp = await litellm.acompletion(**body)
        except Exception as e:
            raise self._map_exception(e) from e

        # LiteLLM returns OpenAI-compatible response format
        choice = resp.choices[0]
        msg = choice.message
        content = msg.content or ""

        # Tool calls
        tcs: list[ToolCall] = []
        raw_tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in raw_tool_calls:
            try:
                fn = tc.function
                params = json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
                tcs.append(ToolCall(id=tc.id, name=fn.name, params=params))
            except Exception as e:
                log.warning(f"LiteLLM: malformed tool_call: {e}")

        # Cost — LiteLLM has built-in cost computation
        cost = 0.0
        try:
            cost = litellm.completion_cost(completion_response=resp)
        except Exception:
            pass  # Some providers don't have cost data

        # Token counts
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tcs,
            cost=float(cost),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=mn,
            finish_reason=choice.finish_reason or "stop",
        )

    async def chat_stream(
        self, messages: list[dict], model: str, tools: list[dict] | None = None, **kw
    ) -> AsyncIterator[str]:
        litellm = self._lazy_import()
        mn = self.get_model(model)
        body: dict[str, Any] = {
            "model": mn,
            "messages": messages,
            "stream": True,
            "temperature": kw.get("temperature", 0.7),
        }
        if "max_tokens" in kw:
            body["max_tokens"] = kw["max_tokens"]
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if self._api_key:
            body["api_key"] = self._api_key
        if self._base_url:
            body["api_base"] = self._base_url

        try:
            stream = await litellm.acompletion(**body)
        except Exception as e:
            raise self._map_exception(e) from e

        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
            except (IndexError, AttributeError):
                continue

    def count_tokens(self, text: str, model: str) -> int:
        """Estimate token count using LiteLLM's tokenizer routing."""
        try:
            litellm = self._lazy_import()
            mn = self.get_model(model)
            return litellm.token_counter(model=mn, text=text)
        except Exception:
            # Fallback: rough chars/4 estimate
            return max(1, len(text) // 4)
