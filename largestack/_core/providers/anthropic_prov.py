"""Anthropic provider (Claude) — real SSE streaming."""
from __future__ import annotations
import json, time
from typing import Any, AsyncIterator
import httpx
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderTimeoutError, ProviderRateLimitError, ProviderError
from largestack.types import LLMResponse, ToolCall

class AnthropicProvider(BaseProvider):
    name = "anthropic"
    def __init__(self, api_key: str):
        self._c = httpx.AsyncClient(base_url="https://api.anthropic.com",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5), http2=True)


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
        mn = self.get_model(model)
        sys_content = ""; user_msgs = []
        for m in messages:
            if m["role"] == "system": sys_content += m["content"] + "\n"
            else: user_msgs.append(m)
        body: dict[str, Any] = {"model": mn, "messages": user_msgs, "max_tokens": max_tokens or 4096, "temperature": temperature}
        if sys_content.strip(): body["system"] = sys_content.strip()
        if tools: body["tools"] = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("parameters", {})} for t in tools]
        # P0.2: forward Anthropic-supported behavior parameters
        if "tool_choice" in kw: body["tool_choice"] = kw["tool_choice"]
        if "top_p" in kw: body["top_p"] = kw["top_p"]
        if "top_k" in kw: body["top_k"] = kw["top_k"]
        if "stop_sequences" in kw: body["stop_sequences"] = kw["stop_sequences"]
        elif "stop" in kw: body["stop_sequences"] = kw["stop"] if isinstance(kw["stop"], list) else [kw["stop"]]
        t0 = time.monotonic()
        try: r = await self._c.post("/v1/messages", json=body)
        except httpx.TimeoutException: raise ProviderTimeoutError(self.name, 120)
        except httpx.RequestError as e: raise ProviderError(f"{self.name} request error: {e}") from e
        ms = (time.monotonic() - t0) * 1000
        if r.status_code == 401: raise ProviderAuthError(self.name)
        if r.status_code in (429, 529): raise ProviderRateLimitError(f"Rate limited by {self.name}")
        if r.status_code >= 400:
            try:
                err_body = r.json(); msg = err_body.get("error", {}).get("message", r.text[:200])
            except Exception: msg = r.text[:200]
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {msg}")
        d = r.json(); u = d.get("usage", {}); content = ""; tcs = []
        for blk in d.get("content", []):
            if blk["type"] == "text": content += blk["text"]
            elif blk["type"] == "tool_use": tcs.append(ToolCall(id=blk["id"], name=blk["name"], params=blk.get("input", {})))
        return LLMResponse(content=content, model=d.get("model", mn), tool_calls=tcs,
            input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
            cached_tokens=u.get("cache_read_input_tokens", 0), latency_ms=ms, finish_reason=d.get("stop_reason", ""))

    async def chat_stream(self, messages, model, tools=None, **kw) -> AsyncIterator[str]:
        """Real SSE streaming via Anthropic /v1/messages with stream=true."""
        mn = self.get_model(model)
        sys_content = ""; user_msgs = []
        for m in messages:
            if m["role"] == "system": sys_content += m["content"] + "\n"
            else: user_msgs.append(m)
        body: dict[str, Any] = {"model": mn, "messages": user_msgs, "max_tokens": 4096, "stream": True}
        if sys_content.strip(): body["system"] = sys_content.strip()
        async with self._c.stream("POST", "/v1/messages", json=body) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "): continue
                raw = line[6:]
                if raw.strip() == "[DONE]": break
                try:
                    event = json.loads(raw)
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield delta["text"]
                except json.JSONDecodeError:
                    continue

    def count_tokens(self, text: str, model: str) -> int: return int(len(text) / 3.5)
    async def close(self): await self._c.aclose()
