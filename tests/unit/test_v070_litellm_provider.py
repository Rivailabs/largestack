"""v0.7.0: LiteLLM provider tests.

Verifies provider construction, model name stripping, exception
mapping, and the lazy-import behavior (no penalty when LiteLLM unused).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_litellm_provider_construction():
    """Provider creates without LiteLLM installed (lazy)."""
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    p = LiteLLMProvider()
    assert p.name == "litellm"
    assert p._litellm is None  # lazy


def test_litellm_strips_only_outer_prefix():
    """``litellm/bedrock/anthropic.claude`` -> ``bedrock/anthropic.claude``"""
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    p = LiteLLMProvider()
    assert p.get_model("litellm/bedrock/anthropic.claude-3-sonnet") == \
        "bedrock/anthropic.claude-3-sonnet"
    assert p.get_model("litellm/cohere/command-r-plus") == "cohere/command-r-plus"
    assert p.get_model("litellm/vertex_ai/gemini-1.5-pro") == "vertex_ai/gemini-1.5-pro"


def test_litellm_raises_clear_error_when_not_installed():
    """If litellm package missing, lazy import raises informative error."""
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    p = LiteLLMProvider()
    with patch.dict("sys.modules", {"litellm": None}):
        with pytest.raises(ImportError, match="pip install litellm"):
            p._lazy_import()


@pytest.mark.asyncio
async def test_litellm_chat_calls_acompletion_correctly():
    """The provider's chat() must call litellm.acompletion with the
    right args and translate the response."""
    from largestack._core.providers.litellm_prov import LiteLLMProvider

    fake_litellm = MagicMock()
    fake_litellm.suppress_debug_info = True
    fake_litellm.AuthenticationError = type("AE", (Exception,), {})
    fake_litellm.RateLimitError = type("RE", (Exception,), {})
    fake_litellm.Timeout = type("TO", (Exception,), {})

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock()]
    fake_resp.choices[0].message.content = "Hello world"
    fake_resp.choices[0].message.tool_calls = None
    fake_resp.choices[0].finish_reason = "stop"
    fake_resp.usage = MagicMock()
    fake_resp.usage.prompt_tokens = 10
    fake_resp.usage.completion_tokens = 5
    fake_litellm.acompletion = AsyncMock(return_value=fake_resp)
    fake_litellm.completion_cost = MagicMock(return_value=0.0001)

    p = LiteLLMProvider()
    p._litellm = fake_litellm  # bypass import

    result = await p.chat(
        messages=[{"role": "user", "content": "Hi"}],
        model="litellm/bedrock/anthropic.claude-3-sonnet",
        temperature=0.5,
    )

    fake_litellm.acompletion.assert_awaited_once()
    call_args = fake_litellm.acompletion.call_args.kwargs
    assert call_args["model"] == "bedrock/anthropic.claude-3-sonnet"
    assert call_args["temperature"] == 0.5
    assert result.content == "Hello world"
    assert result.cost == 0.0001
    assert result.input_tokens == 10
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_litellm_chat_handles_tool_calls():
    """When LiteLLM returns tool_calls, they must be translated to LARGESTACK ToolCall."""
    from largestack._core.providers.litellm_prov import LiteLLMProvider

    fake_litellm = MagicMock()
    fake_litellm.suppress_debug_info = True
    fake_litellm.AuthenticationError = type("AE", (Exception,), {})
    fake_litellm.RateLimitError = type("RE", (Exception,), {})
    fake_litellm.Timeout = type("TO", (Exception,), {})

    tc = MagicMock()
    tc.id = "call_1"
    tc.function.name = "get_weather"
    tc.function.arguments = '{"city": "Bengaluru"}'

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock()]
    fake_resp.choices[0].message.content = ""
    fake_resp.choices[0].message.tool_calls = [tc]
    fake_resp.choices[0].finish_reason = "tool_calls"
    fake_resp.usage = MagicMock()
    fake_resp.usage.prompt_tokens = 20
    fake_resp.usage.completion_tokens = 8
    fake_litellm.acompletion = AsyncMock(return_value=fake_resp)
    fake_litellm.completion_cost = MagicMock(return_value=0)

    p = LiteLLMProvider()
    p._litellm = fake_litellm

    result = await p.chat(
        messages=[{"role": "user", "content": "Weather?"}],
        model="litellm/bedrock/anthropic.claude-3-sonnet",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_weather"
    assert result.tool_calls[0].params == {"city": "Bengaluru"}


def test_litellm_count_tokens_falls_back_on_error():
    """If LiteLLM token_counter fails, fall back to chars/4 estimate."""
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    p = LiteLLMProvider()

    fake_litellm = MagicMock()
    fake_litellm.token_counter = MagicMock(side_effect=Exception("boom"))
    p._litellm = fake_litellm

    text = "a" * 100
    n = p.count_tokens(text, "litellm/openai/gpt-4o-mini")
    assert n == 25  # 100 / 4


def test_litellm_count_tokens_uses_litellm_when_available():
    from largestack._core.providers.litellm_prov import LiteLLMProvider
    p = LiteLLMProvider()
    fake_litellm = MagicMock()
    fake_litellm.token_counter = MagicMock(return_value=42)
    p._litellm = fake_litellm

    n = p.count_tokens("hi", "litellm/openai/gpt-4o-mini")
    assert n == 42


def test_litellm_in_provider_map():
    """Gateway must know about ``litellm`` provider."""
    from largestack._core.gateway import PROVIDER_MAP
    assert "litellm" in PROVIDER_MAP


def test_litellm_provider_in_init_module():
    """Provider must be importable from the package."""
    from largestack._core.providers import LiteLLMProvider  # noqa: F401
