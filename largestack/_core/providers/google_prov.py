"""Google Gemini provider — real SSE streaming."""
from __future__ import annotations
import json, time
from typing import Any, AsyncIterator
import httpx
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderTimeoutError, ProviderRateLimitError, ProviderError
from largestack.types import LLMResponse

class GoogleProvider(BaseProvider):
    name = "google"
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._c = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=30))


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
        contents = []; system_instruction = ""
        for m in messages:
            if m["role"] == "system": system_instruction += m["content"]
            else: contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m.get("content", "")}]})
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": temperature}}
        if max_tokens: body["generationConfig"]["maxOutputTokens"] = max_tokens
        if system_instruction: body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        # P0.2: forward Google structured-output equivalents
        # OpenAI-style response_format → Google responseMimeType + responseSchema
        rf = kw.get("response_format")
        if isinstance(rf, dict):
            if rf.get("type") in ("json_object", "json_schema"):
                body["generationConfig"]["responseMimeType"] = "application/json"
                schema = rf.get("json_schema", {}).get("schema") if rf.get("type") == "json_schema" else None
                if schema:
                    body["generationConfig"]["responseSchema"] = schema
        if "responseMimeType" in kw: body["generationConfig"]["responseMimeType"] = kw["responseMimeType"]
        if "responseSchema" in kw: body["generationConfig"]["responseSchema"] = kw["responseSchema"]
        # v0.3.6: also accept snake_case (matches build_native_params output)
        if "response_mime_type" in kw: body["generationConfig"]["responseMimeType"] = kw["response_mime_type"]
        if "response_schema" in kw: body["generationConfig"]["responseSchema"] = kw["response_schema"]
        if "top_p" in kw: body["generationConfig"]["topP"] = kw["top_p"]
        if "top_k" in kw: body["generationConfig"]["topK"] = kw["top_k"]
        if "stop" in kw: body["generationConfig"]["stopSequences"] = kw["stop"] if isinstance(kw["stop"], list) else [kw["stop"]]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mn}:generateContent?key={self.api_key}"
        t0 = time.monotonic()
        try: r = await self._c.post(url, json=body)
        except httpx.TimeoutException: raise ProviderTimeoutError(self.name, 120)
        except httpx.RequestError as e: raise ProviderError(f"{self.name} request error: {e}") from e
        ms = (time.monotonic() - t0) * 1000
        if r.status_code == 401 or r.status_code == 403: raise ProviderAuthError(self.name)
        if r.status_code == 429: raise ProviderRateLimitError(f"Rate limited by {self.name}")
        if r.status_code >= 400:
            try:
                err_body = r.json(); msg = err_body.get("error", {}).get("message", r.text[:200])
            except Exception: msg = r.text[:200]
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {msg}")
        d = r.json()
        candidate = d.get("candidates", [{}])[0]
        content = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if "text" in p)
        usage = d.get("usageMetadata", {})
        return LLMResponse(content=content, model=mn, input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0), latency_ms=ms, finish_reason=candidate.get("finishReason", ""))

    async def chat_stream(self, messages, model, **kw) -> AsyncIterator[str]:
        """Real SSE streaming via Gemini streamGenerateContent."""
        mn = self.get_model(model)
        contents = []; system_instruction = ""
        for m in messages:
            if m["role"] == "system": system_instruction += m["content"]
            else: contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m.get("content", "")}]})
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": 0.7}}
        if system_instruction: body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mn}:streamGenerateContent?alt=sse&key={self.api_key}"
        async with self._c.stream("POST", url, json=body) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "): continue
                try:
                    chunk = json.loads(line[6:])
                    for candidate in chunk.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("text"): yield part["text"]
                except json.JSONDecodeError:
                    continue

    def count_tokens(self, text, model): return len(text) // 4
    async def close(self): await self._c.aclose()
