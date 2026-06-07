"""v0.5.0: Lazy HTTP client init for providers.

Verifies that creating a provider instance is fast (no eager SSL setup)
and that the HTTP client is created on first access. This is the Agno
"10000x faster" trick — but we're honest: the SSL setup still happens,
just on the first real request.
"""

from __future__ import annotations

import time

import pytest


def test_openai_provider_no_eager_http_client():
    """After __init__, the HTTP client must NOT exist yet."""
    from largestack._core.providers.openai_prov import OpenAIProvider

    p = OpenAIProvider(api_key="sk-test")
    assert p._client is None, "HTTP client should not be created eagerly"


def test_openai_provider_lazy_init_creates_on_access():
    """First access to _c triggers client creation; second access reuses it."""
    from largestack._core.providers.openai_prov import OpenAIProvider

    p = OpenAIProvider(api_key="sk-test")
    c1 = p._c
    c2 = p._c
    assert p._client is not None
    assert c1 is c2, "subsequent access must return the same client (pooled)"


def test_openai_provider_instantiation_is_fast():
    """100 instantiations should take well under 100ms total (1ms each).

    The actual measurement on a typical machine is ~0.3μs each, but we
    allow 1000μs (1ms) of headroom for slow CI runners.
    """
    from largestack._core.providers.openai_prov import OpenAIProvider

    t0 = time.perf_counter_ns()
    for _ in range(100):
        OpenAIProvider(api_key="sk-test")
    avg_us = (time.perf_counter_ns() - t0) / 100 / 1000
    assert avg_us < 1000, f"instantiation too slow: {avg_us:.1f}μs (expected <1000μs)"


def test_azure_provider_lazy_init_with_correct_headers():
    """Azure provider must apply api-key header lazily, not eagerly.

    Regression test for v0.4 → v0.5 refactor: previously Azure poked at
    self._c.headers in __init__, which would defeat the lazy init.
    """
    from largestack._core.providers.azure_prov import AzureOpenAIProvider

    p = AzureOpenAIProvider(
        api_key="sk-azure-test",
        endpoint="https://example.openai.azure.com",
    )
    # Before access: no client
    assert p._client is None

    # Access triggers init, which must produce Azure-style headers
    c = p._c
    assert "api-key" in c.headers
    assert "Authorization" not in c.headers
    assert c.headers["api-key"] == "sk-azure-test"


@pytest.mark.asyncio
async def test_openai_provider_aclose_resets_client():
    """aclose() must close the HTTP client and reset state."""
    from largestack._core.providers.openai_prov import OpenAIProvider

    p = OpenAIProvider(api_key="sk-test")
    _ = p._c  # trigger init
    assert p._client is not None
    await p.aclose()
    assert p._client is None
    # Calling aclose() again must be safe (idempotent)
    await p.aclose()
