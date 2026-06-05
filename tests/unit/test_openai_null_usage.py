"""OpenAI-compatible response parsing must not crash when usage.prompt_tokens_details
is null (NVIDIA and others send it that way). Regression for the AttributeError:
'NoneType' object has no attribute 'get'.
"""
from __future__ import annotations

from largestack._core.providers.openai_prov import OpenAIProvider


class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "prompt_tokens_details": None},
            "model": "x",
        }


class _FakeClient:
    async def post(self, *a, **k):
        return _FakeResp()

    async def aclose(self):
        pass


async def test_parses_response_with_null_prompt_tokens_details():
    p = OpenAIProvider("dummy-key")
    p._client = _FakeClient()  # inject fake (the _c property returns _client if set)
    r = await p.chat([{"role": "user", "content": "hi"}], "x")
    assert r.content == "hi"
    assert r.cached_tokens == 0
