"""Cohere provider — embeddings and reranking."""
from __future__ import annotations
import time
from typing import Any, AsyncIterator
import httpx
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderTimeoutError, ProviderRateLimitError, ProviderError
from largestack.types import LLMResponse

class CohereProvider(BaseProvider):
    name = "cohere"
    def __init__(self, api_key: str):
        self._c = httpx.AsyncClient(
            base_url="https://api.cohere.com/v2",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60)


    async def aclose(self) -> None:
        """Close persistent async HTTP client if present."""
        import asyncio
        import contextlib

        client = getattr(self, "_c", None)
        self._c = None

        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

        with contextlib.suppress(Exception):
            await asyncio.sleep(0)
            await asyncio.sleep(0.10)

    async def close(self) -> None:
        await self.aclose()

    async def chat(self, messages, model, tools=None, stream=False, temperature=0.7, max_tokens=None, **kw) -> LLMResponse:
        mn = self.get_model(model) or "command-r-plus"
        body = {"model": mn, "messages": messages, "temperature": temperature}
        if max_tokens: body["max_tokens"] = max_tokens
        # P0.2: forward Cohere-supported behavior parameters
        if "response_format" in kw: body["response_format"] = kw["response_format"]
        if "tools" in kw and kw["tools"]: body["tools"] = kw["tools"]
        if tools and "tools" not in body: body["tools"] = tools
        if "tool_choice" in kw: body["tool_choice"] = kw["tool_choice"]
        if "p" in kw: body["p"] = kw["p"]
        if "k" in kw: body["k"] = kw["k"]
        if "stop_sequences" in kw: body["stop_sequences"] = kw["stop_sequences"]
        elif "stop" in kw: body["stop_sequences"] = kw["stop"] if isinstance(kw["stop"], list) else [kw["stop"]]
        t0 = time.monotonic()
        try: r = await self._c.post("/chat", json=body)
        except httpx.TimeoutException: raise ProviderTimeoutError(self.name, 60)
        except httpx.RequestError as e: raise ProviderError(f"{self.name} request error: {e}") from e
        ms = (time.monotonic() - t0) * 1000
        if r.status_code == 401: raise ProviderAuthError(self.name)
        if r.status_code == 429: raise ProviderRateLimitError(f"Rate limited by {self.name}")
        if r.status_code >= 400:
            try:
                err_body = r.json(); msg = err_body.get("message", r.text[:200])
            except Exception: msg = r.text[:200]
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {msg}")
        d = r.json()
        content = d.get("message", {}).get("content", [{}])[0].get("text", "")
        usage = d.get("usage", {}).get("tokens", {})
        return LLMResponse(content=content, model=mn,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0), latency_ms=ms)

    async def chat_stream(self, messages, model, **kw) -> AsyncIterator[str]:
        r = await self.chat(messages, model, **kw)
        for c in r.content: yield c

    def count_tokens(self, text, model): return len(text) // 4
