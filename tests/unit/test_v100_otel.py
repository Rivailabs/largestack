"""v0.10.0: Tests for OpenTelemetry instrumentation."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_otel_no_op_when_not_initialized():
    """When OTEL is not set up, spans become no-ops."""
    from largestack._observability.otel import start_span

    # Should not raise even though OTEL not configured
    async with start_span("test.span", attributes={"k": "v"}) as span:
        # No-op span has all expected methods
        span.set_attribute("a", "b")
        span.add_event("event")
        span.set_status("OK")


@pytest.mark.asyncio
async def test_trace_span_decorator_no_op():
    """Decorator works even without OTEL initialized."""
    from largestack._observability.otel import trace_span

    @trace_span("my.fn")
    async def fn(x):
        return x * 2

    result = await fn(5)
    assert result == 10


@pytest.mark.asyncio
async def test_trace_span_propagates_exceptions():
    """Exceptions inside spans should propagate (not be swallowed)."""
    from largestack._observability.otel import trace_span

    @trace_span("failing.fn")
    async def fn():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await fn()


@pytest.mark.asyncio
async def test_trace_llm_call_helper():
    from largestack._observability.otel import trace_llm_call

    async with trace_llm_call(
        provider="openai", model="gpt-4o-mini",
        tenant_id="acme", prompt_tokens=100,
    ) as span:
        # No-op span — just verify it doesn't crash
        span.set_attribute("completion_tokens", 50)


@pytest.mark.asyncio
async def test_trace_tool_call_helper():
    from largestack._observability.otel import trace_tool_call

    async with trace_tool_call(
        tool_name="kyc_verify_pan", tenant_id="acme",
    ) as span:
        span.set_attribute("status", "valid")


@pytest.mark.asyncio
async def test_setup_otel_returns_false_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from largestack._observability.otel import setup_otel
    # No endpoint → return False, don't crash
    assert setup_otel(service_name="test") is False


@pytest.mark.asyncio
async def test_setup_otel_returns_false_without_sdk(monkeypatch):
    """If OTEL SDK isn't installed, return False gracefully."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Mock import failure
    import sys
    saved = {}
    for mod_name in list(sys.modules):
        if mod_name.startswith("opentelemetry"):
            saved[mod_name] = sys.modules.pop(mod_name)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    def fake_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr("builtins.__import__", fake_import)

    try:
        from largestack._observability.otel import setup_otel
        assert setup_otel(service_name="test") is False
    finally:
        sys.modules.update(saved)


def test_is_initialized():
    from largestack._observability.otel import is_initialized
    # By default, not initialized
    assert isinstance(is_initialized(), bool)


def test_get_tracer_when_not_initialized():
    from largestack._observability.otel import get_tracer
    # May be None when not set up
    result = get_tracer()
    assert result is None or hasattr(result, "start_as_current_span")
