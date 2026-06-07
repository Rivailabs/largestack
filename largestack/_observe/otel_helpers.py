"""OpenTelemetry helpers for span linking and trace context propagation (v0.6.0).

Existing OTel setup creates spans but doesn't expose helpers for:
1. **Linking spans across runs** — when one agent run is causally related
   to another (e.g. a user asks a question, the answer triggers a
   follow-up agent run). Linked spans show up correctly in Jaeger/Tempo.
2. **W3C trace context propagation** — for distributed tracing across
   services. Lets you inject trace headers into outgoing HTTP requests
   and extract them from incoming ones, so a single trace flows through
   your microservices.

Usage:

    from largestack._observe.otel_helpers import (
        link_to_current_span, get_traceparent_header, with_traceparent
    )

    # In a child agent run that's caused by a parent run's output:
    parent_trace_id = parent_result.trace_id  # 128-bit hex
    parent_span_id = parent_result.span_id    # 64-bit hex
    span = link_to_current_span(parent_trace_id, parent_span_id, "follow_up")

    # Distributed tracing — inject into HTTP request headers:
    headers = {"Content-Type": "application/json"}
    headers.update(get_traceparent_header())
    requests.post("http://other-service/api", headers=headers)

    # On the receiver:
    traceparent = request.headers.get("traceparent")
    with with_traceparent(traceparent):
        result = await agent.run(...)  # uses the propagated trace
"""

from __future__ import annotations
import logging
import re
from contextlib import contextmanager
from typing import Iterator

log = logging.getLogger("largestack.otel_helpers")


def _try_otel():
    """Import OpenTelemetry, returning (trace, SpanContext) or (None, None)."""
    try:
        from opentelemetry import trace
        from opentelemetry.trace import SpanContext, TraceFlags, Link

        return trace, SpanContext, TraceFlags, Link
    except ImportError:
        return None, None, None, None


def link_to_current_span(
    trace_id_hex: str,
    span_id_hex: str,
    span_name: str = "linked_span",
):
    """Open a new span that is *linked* to a remote span.

    Used when:
    - A parent agent's result triggers a child agent run
    - You want both runs to appear in the same trace tree

    Returns the new span (caller is responsible for ``span.end()`` —
    typically via ``with link_to_current_span(...) as s:``). If OTel
    isn't installed, returns a no-op context manager.

    Args:
        trace_id_hex: 32-char hex (OTel TraceId).
        span_id_hex: 16-char hex (OTel SpanId).
        span_name: name for the new span.
    """
    trace, SpanContext, TraceFlags, Link = _try_otel()
    if trace is None:
        return _noop_span()

    if not _valid_hex(trace_id_hex, 32) or not _valid_hex(span_id_hex, 16):
        log.warning(f"link_to_current_span: invalid IDs ({trace_id_hex!r}, {span_id_hex!r})")
        return _noop_span()

    parent_ctx = SpanContext(
        trace_id=int(trace_id_hex, 16),
        span_id=int(span_id_hex, 16),
        is_remote=True,
        trace_flags=TraceFlags(0x01),  # SAMPLED
    )
    link = Link(parent_ctx)
    tracer = trace.get_tracer("largestack")
    return tracer.start_as_current_span(span_name, links=[link])


def get_traceparent_header() -> dict:
    """Return ``{"traceparent": "00-..."}`` for the currently active span.

    Empty dict if no active span or OTel not installed. Callers append
    this to outgoing HTTP request headers for distributed tracing.

    The format is W3C Trace Context: 00-{trace_id}-{span_id}-{flags}.
    """
    trace, *_ = _try_otel()
    if trace is None:
        return {}
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if not ctx or not ctx.is_valid:
        return {}
    traceparent = f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{ctx.trace_flags:02x}"
    return {"traceparent": traceparent}


_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def parse_traceparent(header: str) -> tuple[str, str, int] | None:
    """Parse a W3C traceparent header. Returns (trace_id, span_id, flags) or None."""
    if not header:
        return None
    m = _TRACEPARENT_RE.match(header.strip().lower())
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3), 16)


@contextmanager
def with_traceparent(traceparent: str | None) -> Iterator[None]:
    """Context manager that adopts a remote trace context for spans inside.

    Used in incoming HTTP handlers to attach the local agent run to a
    distributed trace started elsewhere. If the header is missing or OTel
    isn't installed, this is a no-op (yields immediately).
    """
    trace, SpanContext, TraceFlags, Link = _try_otel()
    if trace is None or not traceparent:
        yield
        return

    parsed = parse_traceparent(traceparent)
    if parsed is None:
        log.debug(f"with_traceparent: malformed header: {traceparent!r}")
        yield
        return

    trace_id, span_id, flags = parsed
    parent_ctx = SpanContext(
        trace_id=int(trace_id, 16),
        span_id=int(span_id, 16),
        is_remote=True,
        trace_flags=TraceFlags(flags),
    )
    from opentelemetry.trace import set_span_in_context, NonRecordingSpan
    from opentelemetry import context as otel_ctx

    span = NonRecordingSpan(parent_ctx)
    ctx = set_span_in_context(span)
    token = otel_ctx.attach(ctx)
    try:
        yield
    finally:
        otel_ctx.detach(token)


# -------------------- helpers --------------------


def _valid_hex(s: str, length: int) -> bool:
    if not isinstance(s, str) or len(s) != length:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


@contextmanager
def _noop_span() -> Iterator[None]:
    """No-op replacement when OTel isn't available."""
    yield None
