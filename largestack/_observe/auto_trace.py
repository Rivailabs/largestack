"""Auto-instrumentation — monkey-patch httpx to trace all LLM calls."""

from __future__ import annotations
import logging, time, functools

log = logging.getLogger("largestack.auto_trace")
_patched = False


def patch_httpx():
    """Monkey-patch httpx.AsyncClient to auto-trace all HTTP calls."""
    global _patched
    if _patched:
        return

    try:
        import httpx
        from opentelemetry import trace

        tracer = trace.get_tracer("largestack.http")
        original_send = httpx.AsyncClient.send

        @functools.wraps(original_send)
        async def traced_send(self, request, **kwargs):
            url = str(request.url)
            # Detect LLM provider from URL
            provider = "unknown"
            if "openai.com" in url:
                provider = "openai"
            elif "anthropic.com" in url:
                provider = "anthropic"
            elif "deepseek.com" in url:
                provider = "deepseek"
            elif "localhost:11434" in url:
                provider = "ollama"
            elif "generativelanguage" in url:
                provider = "google"

            span_name = (
                "gen_ai.chat" if "/chat" in url or "/messages" in url else f"http.{request.method}"
            )

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("gen_ai.provider.name", provider)
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.url", url[:200])

                t0 = time.monotonic()
                response = await original_send(self, request, **kwargs)
                latency = (time.monotonic() - t0) * 1000

                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("gen_ai.response.latency_ms", latency)

                return response

        httpx.AsyncClient.send = traced_send
        _patched = True
        log.info("httpx auto-instrumentation active")
    except ImportError:
        log.debug("OpenTelemetry not installed, skipping auto-trace")


def patch_all():
    """Patch all supported libraries."""
    patch_httpx()
