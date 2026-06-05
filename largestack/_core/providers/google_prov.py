"""Google Gemini provider — real SSE streaming."""
from __future__ import annotations
import json, time
from typing import Any, AsyncIterator
import httpx
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderAuthError, ProviderTimeoutError, ProviderRateLimitError, ProviderError
from largestack.types import LLMResponse, ToolCall

# Gemini accepts only a subset of JSON Schema for function parameters.
_SCHEMA_DROP = {"additionalProperties", "$schema", "title", "default", "examples"}


def _clean_schema(schema):
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k in _SCHEMA_DROP:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {pk: _clean_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _clean_schema(v)
        else:
            out[k] = v
    return out


def _to_gemini_contents(messages):
    """Translate OpenAI-style messages (incl. tool calls/results) into Gemini contents.

    The engine's tool-result messages carry tool_call_id (not the function name) that
    Gemini needs, so we map id -> name from the preceding assistant tool_calls.
    """
    contents = []
    system_instruction = ""
    id_to_name = {}
    for m in messages:
        role = m.get("role")
        if role == "system":
            system_instruction += (m.get("content") or "") + "\n"
        elif role == "assistant" and m.get("tool_calls"):
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                id_to_name[tc.get("id")] = name
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                parts.append({"functionCall": {"name": name, "args": args}})
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            name = id_to_name.get(m.get("tool_call_id")) or m.get("name") or "tool"
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": name, "response": {"result": m.get("content", "")}}}
            ]})
        else:
            grole = "user" if role == "user" else "model"
            contents.append({"role": grole, "parts": [{"text": m.get("content", "")}]})
    return contents, system_instruction.strip()


class GoogleProvider(BaseProvider):
    name = "google"
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._c = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5))


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
        contents, system_instruction = _to_gemini_contents(messages)
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": temperature}}
        if max_tokens: body["generationConfig"]["maxOutputTokens"] = max_tokens
        if system_instruction: body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if tools:
            body["tools"] = [{"function_declarations": [
                {"name": t["name"], "description": t.get("description", ""),
                 "parameters": _clean_schema(t.get("parameters") or {"type": "object", "properties": {}})}
                for t in tools
            ]}]
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
        content = ""; tcs = []
        for p in candidate.get("content", {}).get("parts", []):
            if "text" in p:
                content += p["text"]
            elif "functionCall" in p:
                fc = p["functionCall"]
                tcs.append(ToolCall(id=f"call_{len(tcs)}", name=fc.get("name", ""), params=fc.get("args", {}) or {}))
        usage = d.get("usageMetadata", {})
        return LLMResponse(content=content, model=mn, tool_calls=tcs,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0), latency_ms=ms,
            finish_reason=candidate.get("finishReason", ""))

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
