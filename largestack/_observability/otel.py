"""OpenTelemetry instrumentation (v0.10.0).

Wraps the agent / tool execution paths in OTEL spans so traces show up
in Jaeger / Tempo / Honeycomb / Datadog. Optional dependency — the
module degrades gracefully (no-ops) if ``opentelemetry-api`` isn't
installed.

Usage::

    from largestack._observability.otel import setup_otel, tracer

    setup_otel(
        service_name="largestack-fintech",
        endpoint="http://otel-collector:4317",
    )

    @trace_span("kyc.verify_pan")
    async def verify_pan(pan: str):
        ...

Or as a context manager::

    async with start_span("rag.retrieve", attributes={"k": 5}):
        results = await retriever(query)
"""
from __future__ import annotations
import contextlib
import functools
import logging
import os
from typing import Any, AsyncIterator, Callable

log = logging.getLogger("largestack.otel")


# These are populated when setup_otel is called
_tracer = None
_initialized = False


def is_initialized() -> bool:
    """Whether OTEL has been set up."""
    return _initialized


def setup_otel(
    *,
    service_name: str = "largestack-agent",
    endpoint: str | None = None,
    headers: dict | None = None,
    insecure: bool = True,
    sample_rate: float = 1.0,
) -> bool:
    """Initialize OpenTelemetry tracer + OTLP exporter.

    Args:
        service_name: shown in trace UI
        endpoint: OTLP collector URL (else OTEL_EXPORTER_OTLP_ENDPOINT env)
        headers: optional auth headers (e.g. for Honeycomb API key)
        insecure: whether to use insecure gRPC (default True for local)
        sample_rate: 0.0-1.0 fraction of traces to keep

    Returns:
        True if OTEL was successfully initialized, False if deps missing.
    """
    global _tracer, _initialized

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        log.info("OpenTelemetry SDK not installed; tracing disabled")
        return False

    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        log.info("No OTEL_EXPORTER_OTLP_ENDPOINT; tracing disabled")
        return False

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint, headers=headers, insecure=insecure,
        )
    except ImportError:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        except ImportError:
            log.warning("OTLP exporter not installed; tracing disabled")
            return False

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(sample_rate),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("largestack")
    _initialized = True
    log.info(f"OTEL initialized: {service_name} → {endpoint}")
    return True


def get_tracer():
    """Return the configured tracer or None if not initialized."""
    return _tracer


@contextlib.asynccontextmanager
async def start_span(
    name: str, attributes: dict | None = None,
) -> AsyncIterator:
    """Start an OTEL span. Becomes a no-op if OTEL isn't initialized.

    Usage::

        async with start_span("rag.retrieve", attributes={"k": 5}):
            ...
    """
    if _tracer is None:
        # No-op span
        class _NoOpSpan:
            def set_attribute(self, *a, **kw): pass
            def add_event(self, *a, **kw): pass
            def record_exception(self, *a, **kw): pass
            def set_status(self, *a, **kw): pass
        yield _NoOpSpan()
        return

    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v)
                except Exception:
                    span.set_attribute(k, str(v))
        try:
            yield span
        except Exception as e:
            try:
                span.record_exception(e)
                # Try to set ERROR status if supported
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR, str(e)))
            except ImportError:
                pass
            raise


def trace_span(name: str | None = None, attributes: dict | None = None):
    """Decorator that wraps an async function in an OTEL span."""
    def decorator(fn: Callable[..., Any]):
        span_name = name or f"{fn.__module__}.{fn.__name__}"

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with start_span(span_name, attributes=attributes) as span:
                # Attach call args summary as attributes (truncated)
                try:
                    span.set_attribute("largestack.fn.args.count", len(args))
                    span.set_attribute("largestack.fn.kwargs.count", len(kwargs))
                except Exception:
                    pass
                return await fn(*args, **kwargs)
        return wrapper

    return decorator


# -------------------- Instrument LLM call helper --------------------

@contextlib.asynccontextmanager
async def trace_llm_call(
    *,
    provider: str,
    model: str,
    tenant_id: str | None = None,
    prompt_tokens: int | None = None,
) -> AsyncIterator:
    """Specialized span for LLM calls — sets standard attributes.

    Usage::

        async with trace_llm_call(provider="openai", model="gpt-4o-mini") as span:
            response = await openai.chat.completions.create(...)
            span.set_attribute("largestack.llm.completion_tokens", response.usage.completion_tokens)
    """
    attrs: dict = {
        "largestack.llm.provider": provider,
        "largestack.llm.model": model,
    }
    if tenant_id:
        attrs["largestack.tenant_id"] = tenant_id
    if prompt_tokens is not None:
        attrs["largestack.llm.prompt_tokens"] = prompt_tokens

    async with start_span(f"llm.{provider}.{model}", attributes=attrs) as span:
        yield span


# -------------------- Instrument tool call helper --------------------

@contextlib.asynccontextmanager
async def trace_tool_call(
    *,
    tool_name: str,
    tenant_id: str | None = None,
) -> AsyncIterator:
    attrs: dict = {"largestack.tool.name": tool_name}
    if tenant_id:
        attrs["largestack.tenant_id"] = tenant_id
    async with start_span(f"tool.{tool_name}", attributes=attrs) as span:
        yield span
