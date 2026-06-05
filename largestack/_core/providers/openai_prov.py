"""OpenAI provider (GPT-4o, GPT-5, o3).

v0.5.0: HTTP client creation is deferred until the first request so that
`Agent("openai/gpt-4o")` returns in microseconds instead of milliseconds.
This matches the Agno benchmark trick — the SSL setup still happens, but
on the first network call rather than during construction. For workloads
that create many short-lived agents, this is a real win. For a single
long-lived agent, the difference is unobservable (one-time cost of ~10ms).
"""
from __future__ import annotations
import json, logging, time
from typing import Any, AsyncIterator
import httpx

LARGESTACK_HTTP_LIMITS_NO_KEEPALIVE = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=0,
    keepalive_expiry=0.0,
)

from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderTimeoutError, ProviderRateLimitError, ProviderError
from largestack.types import LLMResponse, ToolCall

log = logging.getLogger("largestack.providers.openai")

class OpenAIProvider(BaseProvider):
    name = "openai"
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self._api_key = api_key
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def _c(self) -> httpx.AsyncClient:
        """Lazy-initialize HTTP client on first access.

        v0.5.0: avoids the ~10ms ssl.create_default_context() penalty during
        Agent construction. The client is shared across all calls to this
        provider instance (correct for httpx — it's connection-pooled).
        """
        if self._client is None:
            self._client = httpx.AsyncClient(limits=LARGESTACK_HTTP_LIMITS_NO_KEEPALIVE, 
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5),
                http2=True,
            )
        return self._client


    async def close(self) -> None:
        """Async close alias."""
        await self.aclose()


    async def aclose(self) -> None:
        """Close underlying async HTTP client and settle transports."""
        import asyncio
        import contextlib

        client = getattr(self, "_client", None)
        self._client = None

        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

        with contextlib.suppress(Exception):
            await asyncio.sleep(0)
            await asyncio.sleep(0.25)

    async def chat(self, messages, model, tools=None, stream=False, temperature=0.7, max_tokens=None, **kw) -> LLMResponse:
        mn = self.get_model(model)
        body: dict[str, Any] = {"model": mn, "messages": messages, "temperature": temperature}
        if max_tokens: body["max_tokens"] = max_tokens
        if tools: body["tools"] = [{"type": "function", "function": t} for t in tools]
        # P0.2: forward structured output + tool routing parameters
        if "response_format" in kw: body["response_format"] = kw["response_format"]
        if "tool_choice" in kw: body["tool_choice"] = kw["tool_choice"]
        if "seed" in kw: body["seed"] = kw["seed"]
        if "top_p" in kw: body["top_p"] = kw["top_p"]
        if "stop" in kw: body["stop"] = kw["stop"]
        t0 = time.monotonic()
        try:
            r = await self._c.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, 120)
        except httpx.RequestError as e:
            raise ProviderError(f"{self.name} request error: {e}") from e
        ms = (time.monotonic() - t0) * 1000
        if r.status_code == 401: raise ProviderAuthError(self.name)
        if r.status_code == 429: raise ProviderRateLimitError(f"Rate limited by {self.name}")
        # P0.6: wrap any HTTP error into ProviderError so fallback can catch it
        if r.status_code >= 400:
            try:
                err_body = r.json()
                msg = err_body.get("error", {}).get("message", r.text[:200])
            except Exception:
                msg = r.text[:200]
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {msg}")
        try:
            d = r.json(); ch = d["choices"][0]; msg = ch["message"]; u = d.get("usage", {})
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise ProviderError(f"{self.name} response parse error: {e}") from e
        tcs = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                # Guard malformed tool-call JSON
                try:
                    params = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    log.warning(f"{self.name}: malformed tool-call JSON marked as provider_output_error")
                    params = {"__largestack_error__": "malformed_tool_call_json"}
                tcs.append(ToolCall(id=tc["id"], name=tc["function"]["name"], params=params))
        return LLMResponse(content=msg.get("content") or "", model=d.get("model", mn), tool_calls=tcs,
            reasoning_content=msg.get("reasoning_content"),
            input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0),
            cached_tokens=u.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            latency_ms=ms, finish_reason=ch.get("finish_reason", ""))

    async def chat_stream(self, messages, model, tools=None, **kw) -> AsyncIterator[str]:
        mn = self.get_model(model)
        body = {"model": mn, "messages": messages, "stream": True}
        if tools: body["tools"] = [{"type": "function", "function": t} for t in tools]
        async with self._c.stream("POST", "/chat/completions", json=body) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    raw = line[6:]
                    if raw == "[DONE]": break
                    try:
                        delta = json.loads(raw)["choices"][0].get("delta", {})
                        if delta.get("content"): yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    def count_tokens(self, text: str, model: str) -> int:
        try:
            import tiktoken; return len(tiktoken.encoding_for_model(self.get_model(model)).encode(text))
        except Exception: return len(text) // 4
