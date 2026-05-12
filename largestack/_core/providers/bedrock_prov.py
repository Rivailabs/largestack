"""AWS Bedrock provider — async-safe via run_in_executor for sync boto3."""
from __future__ import annotations
import asyncio, json, time
from typing import Any, AsyncIterator
from largestack._core.providers.base import BaseProvider
from largestack.errors import ProviderError, ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError
from largestack.types import LLMResponse

class BedrockProvider(BaseProvider):
    name = "bedrock"
    def __init__(self, region: str = "us-east-1"):
        self.region = region; self._client = None
        try:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=region)
        except ImportError: pass

    def _ensure_client(self):
        # P0-3b (v0.3.3): wrap missing boto3 into ProviderError so fallback works
        if not self._client:
            raise ProviderError(f"{self.name}: boto3 not installed (pip install boto3)")

    @staticmethod
    def _normalize_aws_error(e: Exception) -> Exception:
        """Map botocore/boto3 errors into the ProviderError hierarchy."""
        try:
            from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError
            if isinstance(e, (ConnectTimeoutError, ReadTimeoutError)):
                return ProviderTimeoutError("bedrock", 120)
            if isinstance(e, EndpointConnectionError):
                return ProviderError(f"bedrock connection error: {e}")
            if isinstance(e, ClientError):
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("UnrecognizedClientException", "InvalidSignatureException", "AuthFailure"):
                    return ProviderAuthError("bedrock")
                if code in ("ThrottlingException", "TooManyRequestsException"):
                    return ProviderRateLimitError("Rate limited by bedrock")
                return ProviderError(f"bedrock {code}: {e}")
        except ImportError:
            pass
        return ProviderError(f"bedrock error: {e}")

    async def chat(self, messages, model, tools=None, stream=False, temperature=0.7, max_tokens=None, **kw) -> LLMResponse:
        self._ensure_client()
        mn = self.get_model(model)
        body = {"messages": messages, "max_tokens": max_tokens or 4096, "temperature": temperature,
                "anthropic_version": "bedrock-2023-05-31"}
        sys_msgs = [m for m in messages if m["role"] == "system"]
        if sys_msgs:
            body["system"] = [{"text": m["content"]} for m in sys_msgs]
            body["messages"] = [m for m in messages if m["role"] != "system"]
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        try:
            resp = await loop.run_in_executor(None, lambda: self._client.invoke_model(
                modelId=mn, body=json.dumps(body)))
        except Exception as e:
            raise self._normalize_aws_error(e) from e
        ms = (time.monotonic() - t0) * 1000
        try:
            raw = await loop.run_in_executor(None, resp["body"].read)
            data = json.loads(raw)
        except Exception as e:
            raise ProviderError(f"bedrock response parse error: {e}") from e
        content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return LLMResponse(content=content, model=mn, input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0), latency_ms=ms)

    async def chat_stream(self, messages, model, tools=None, **kw) -> AsyncIterator[str]:
        self._ensure_client()
        mn = self.get_model(model)
        body = {"messages": messages, "max_tokens": 4096, "anthropic_version": "bedrock-2023-05-31"}
        sys_msgs = [m for m in messages if m["role"] == "system"]
        if sys_msgs:
            body["system"] = [{"text": m["content"]} for m in sys_msgs]
            body["messages"] = [m for m in messages if m["role"] != "system"]
        loop = asyncio.get_running_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: self._client.invoke_model_with_response_stream(
                modelId=mn, body=json.dumps(body)))
            def _read_stream():
                chunks = []
                for event in resp.get("body", []):
                    raw = event.get("chunk", {}).get("bytes", b"{}")
                    chunk = json.loads(raw)
                    if chunk.get("type") == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            chunks.append(delta["text"])
                return chunks
            chunks = await loop.run_in_executor(None, _read_stream)
            for chunk in chunks:
                yield chunk
        except (ProviderError, ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError):
            raise
        except Exception as e:
            try:
                resp = await self.chat(messages, model, tools, **kw)
                yield resp.content
            except Exception as e2:
                raise self._normalize_aws_error(e2) from e2

    def count_tokens(self, text, model): return len(text) // 4
