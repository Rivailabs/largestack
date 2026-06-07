"""v0.13.0: Tests for LiteLLM bridge."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- Module imports --------------------


def test_litellm_bridge_imports():
    from largestack._integrations import litellm_bridge

    assert hasattr(litellm_bridge, "LiteLLMProvider")
    assert hasattr(litellm_bridge, "FallbackRouter")


# -------------------- Construction --------------------


def test_provider_construction_basic():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    p = LiteLLMProvider(model="openai/gpt-4o-mini", api_key="sk-test")
    assert p.model == "openai/gpt-4o-mini"
    assert p.api_key == "sk-test"


def test_provider_extracts_provider_prefix():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    assert LiteLLMProvider("openai/gpt-4o")._provider_prefix() == "openai"
    assert (
        LiteLLMProvider(
            "bedrock/anthropic.claude-3-5",
        )._provider_prefix()
        == "bedrock"
    )
    # Bare model = OpenAI default
    assert LiteLLMProvider("gpt-4o")._provider_prefix() == "openai"


# -------------------- India residency check --------------------


def test_india_residency_blocks_china_provider():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    with pytest.raises(ValueError, match="China-hosted"):
        LiteLLMProvider(
            model="deepseek/chat",
            require_india_residency=True,
        )


def test_india_residency_blocks_moonshot():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    with pytest.raises(ValueError, match="China-hosted"):
        LiteLLMProvider(
            model="moonshot/kimi-k2",
            require_india_residency=True,
        )


def test_india_residency_allows_bedrock_mumbai():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    p = LiteLLMProvider(
        model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        region="ap-south-1",
        require_india_residency=True,
    )
    assert p.region == "ap-south-1"


def test_india_residency_blocks_bedrock_us_region():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    with pytest.raises(ValueError, match="ap-south"):
        LiteLLMProvider(
            model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
            region="us-east-1",
            require_india_residency=True,
        )


def test_india_residency_allows_azure():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    # Azure passes (no region check applied — caller picks India deploy)
    p = LiteLLMProvider(
        model="azure/gpt-4o",
        require_india_residency=True,
    )
    assert p.model == "azure/gpt-4o"


def test_residency_disabled_allows_china():
    """When residency check is off, China providers are allowed."""
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    # Should not raise
    p = LiteLLMProvider(
        model="deepseek/chat",
        require_india_residency=False,
    )
    assert p.model == "deepseek/chat"


# -------------------- _build_kwargs --------------------


def test_build_kwargs_includes_api_key():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    p = LiteLLMProvider(
        model="openai/gpt-4o",
        api_key="sk-test",
    )
    kwargs = p._build_kwargs([{"role": "user", "content": "hi"}])
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["model"] == "openai/gpt-4o"


def test_build_kwargs_bedrock_passes_region():
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    p = LiteLLMProvider(
        model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        region="ap-south-1",
    )
    kwargs = p._build_kwargs([])
    assert kwargs["aws_region_name"] == "ap-south-1"


# -------------------- acomplete (mocked litellm) --------------------


@pytest.mark.asyncio
async def test_acomplete_raises_without_litellm():
    from largestack._integrations import litellm_bridge
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    with patch.object(
        litellm_bridge,
        "_have_litellm",
        return_value=False,
    ):
        p = LiteLLMProvider(model="openai/gpt-4o")
        with pytest.raises(ImportError, match="litellm"):
            await p.acomplete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_acomplete_normalises_response():
    from largestack._integrations import litellm_bridge
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hello world"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=5,
            completion_tokens=2,
            total_tokens=7,
        ),
        model="openai/gpt-4o-mini",
    )

    fake_litellm = MagicMock()
    fake_litellm.acompletion = AsyncMock(return_value=fake_resp)

    with (
        patch.object(
            litellm_bridge,
            "_have_litellm",
            return_value=True,
        ),
        patch.dict(
            sys.modules,
            {"litellm": fake_litellm},
        ),
    ):
        p = LiteLLMProvider(model="openai/gpt-4o-mini")
        resp = await p.acomplete([{"role": "user", "content": "hi"}])

    assert resp.content == "hello world"
    assert resp.finish_reason == "stop"
    assert resp.usage["total_tokens"] == 7


@pytest.mark.asyncio
async def test_acomplete_handles_missing_usage():
    """Some providers don't return usage; bridge should handle it."""
    from largestack._integrations import litellm_bridge
    from largestack._integrations.litellm_bridge import LiteLLMProvider

    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="x"),
                finish_reason="stop",
            )
        ],
        model="ollama/llama3",
        usage=None,
    )

    fake_litellm = MagicMock()
    fake_litellm.acompletion = AsyncMock(return_value=fake_resp)

    with (
        patch.object(
            litellm_bridge,
            "_have_litellm",
            return_value=True,
        ),
        patch.dict(sys.modules, {"litellm": fake_litellm}),
    ):
        p = LiteLLMProvider(model="ollama/llama3")
        resp = await p.acomplete([{"role": "user", "content": "hi"}])

    assert resp.usage == {}


# -------------------- FallbackRouter --------------------


@pytest.mark.asyncio
async def test_router_returns_first_success():
    from largestack._integrations.litellm_bridge import (
        FallbackRouter,
        ProviderRoute,
        LiteLLMResponse,
    )

    p1 = MagicMock()
    p1.acomplete = AsyncMock(
        return_value=LiteLLMResponse(content="from p1", model="m1"),
    )
    p2 = MagicMock()
    p2.acomplete = AsyncMock(side_effect=RuntimeError("never called"))

    router = FallbackRouter(
        [
            ProviderRoute(provider=p1, label="primary"),
            ProviderRoute(provider=p2, label="fallback"),
        ]
    )
    resp = await router.acomplete([])
    assert resp.content == "from p1"
    p2.acomplete.assert_not_called()


@pytest.mark.asyncio
async def test_router_falls_through_to_next_provider():
    from largestack._integrations.litellm_bridge import (
        FallbackRouter,
        ProviderRoute,
        LiteLLMResponse,
    )

    p1 = MagicMock()
    p1.acomplete = AsyncMock(side_effect=RuntimeError("p1 down"))
    p2 = MagicMock()
    p2.acomplete = AsyncMock(
        return_value=LiteLLMResponse(content="from p2", model="m2"),
    )

    router = FallbackRouter(
        [
            ProviderRoute(provider=p1, label="primary"),
            ProviderRoute(provider=p2, label="fallback"),
        ]
    )
    resp = await router.acomplete([])
    assert resp.content == "from p2"
    p1.acomplete.assert_called_once()


@pytest.mark.asyncio
async def test_router_raises_when_all_fail():
    from largestack._integrations.litellm_bridge import (
        FallbackRouter,
        ProviderRoute,
    )

    p1 = MagicMock()
    p1.acomplete = AsyncMock(side_effect=RuntimeError("p1 down"))
    p2 = MagicMock()
    p2.acomplete = AsyncMock(side_effect=RuntimeError("p2 down"))

    router = FallbackRouter(
        [
            ProviderRoute(provider=p1, label="primary"),
            ProviderRoute(provider=p2, label="fallback"),
        ]
    )
    with pytest.raises(RuntimeError, match="all 2 providers failed"):
        await router.acomplete([])


@pytest.mark.asyncio
async def test_router_invokes_on_failure_callback():
    from largestack._integrations.litellm_bridge import (
        FallbackRouter,
        ProviderRoute,
        LiteLLMResponse,
    )

    p1 = MagicMock()
    p1.acomplete = AsyncMock(side_effect=RuntimeError("primary down"))
    p2 = MagicMock()
    p2.acomplete = AsyncMock(
        return_value=LiteLLMResponse(content="ok", model="m2"),
    )

    failures = []
    router = FallbackRouter(
        [
            ProviderRoute(provider=p1, label="primary"),
            ProviderRoute(provider=p2, label="fallback"),
        ],
        on_failure=lambda label, exc: failures.append((label, str(exc))),
    )
    await router.acomplete([])
    assert len(failures) == 1
    assert failures[0][0] == "primary"
    assert "down" in failures[0][1]


def test_router_requires_at_least_one_route():
    from largestack._integrations.litellm_bridge import FallbackRouter

    with pytest.raises(ValueError, match="at least one"):
        FallbackRouter([])
