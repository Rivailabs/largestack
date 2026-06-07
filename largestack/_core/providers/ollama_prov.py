"""Ollama provider (local models)."""

from __future__ import annotations
import json, time
from typing import Any, AsyncIterator
import httpx
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderError, ProviderTimeoutError
from largestack.types import LLMResponse


class OllamaProvider(BaseProvider):
    name = "ollama"
    supports_tools = False

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._c = httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(connect=5, read=300, write=30, pool=5)
        )

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

    async def chat(
        self, messages, model, tools=None, stream=False, temperature=0.7, max_tokens=None, **kw
    ) -> LLMResponse:
        mn = self.get_model(model)
        body: dict[str, Any] = {
            "model": mn,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            body["options"]["num_predict"] = max_tokens
        # v1.1.1: native structured outputs — Ollama accepts `format` as "json" or a
        # JSON schema (constrained decoding), which makes typed output reliable even on
        # small local models. Passed through by structured.build_native_params.
        _fmt = kw.get("format")
        if _fmt is not None:
            body["format"] = _fmt
        t0 = time.monotonic()
        # P0-3a (v0.3.3): wrap all transport + HTTP failures into ProviderError so fallback works
        try:
            r = await self._c.post("/api/chat", json=body)
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, 300)
        except httpx.RequestError as e:
            raise ProviderError(f"{self.name} request error: {e}") from e
        ms = (time.monotonic() - t0) * 1000
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {r.text[:200]}")
        try:
            d = r.json()
        except json.JSONDecodeError as e:
            raise ProviderError(f"{self.name} response parse error: {e}") from e
        return LLMResponse(
            content=d.get("message", {}).get("content", ""),
            model=mn,
            input_tokens=d.get("prompt_eval_count", 0),
            output_tokens=d.get("eval_count", 0),
            latency_ms=ms,
            finish_reason="stop" if d.get("done") else "length",
        )

    async def chat_stream(self, messages, model, **kw) -> AsyncIterator[str]:
        mn = self.get_model(model)
        try:
            async with self._c.stream(
                "POST", "/api/chat", json={"model": mn, "messages": messages, "stream": True}
            ) as r:
                async for line in r.aiter_lines():
                    if line:
                        try:
                            ch = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if ch.get("message", {}).get("content"):
                            yield ch["message"]["content"]
                        if ch.get("done"):
                            break
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.name, 300)
        except httpx.RequestError as e:
            raise ProviderError(f"{self.name} request error: {e}") from e

    def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4
