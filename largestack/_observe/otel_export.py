"""OpenTelemetry exporters — send traces to Langfuse, Jaeger, OTLP collectors.

Replaces SQLite-only export. Production teams use real observability platforms.

Usage:
    # In largestack.yaml:
    trace_backend: langfuse   # or: otlp, jaeger, sqlite (default)
    langfuse_public_key: pk-lf-...
    langfuse_secret_key: sk-lf-...
    
    # Or programmatically:
    from largestack._observe.otel_export import setup_exporter
    setup_exporter("langfuse", public_key="...", secret_key="...")
"""
from __future__ import annotations
import os, logging
from typing import Any

log = logging.getLogger("largestack.otel_export")

def setup_exporter(backend: str = "sqlite", **config) -> Any:
    """Configure trace exporter. Returns the SpanExporter instance."""
    backend = backend.lower()

    if backend == "otlp":
        return _setup_otlp(config)
    elif backend == "langfuse":
        return _setup_langfuse(config)
    elif backend == "jaeger":
        return _setup_jaeger(config)
    elif backend == "console":
        return _setup_console()
    else:
        return _setup_sqlite(config)

def _setup_otlp(config: dict) -> Any:
    """OTLP gRPC/HTTP exporter — works with Jaeger, Grafana Tempo, Datadog, etc."""
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        endpoint = config.get("endpoint") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint)
        _register(exporter)
        log.info(f"OTLP exporter → {endpoint}")
        return exporter
    except ImportError:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            endpoint = config.get("endpoint") or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
            exporter = OTLPSpanExporter(endpoint=endpoint)
            _register(exporter)
            log.info(f"OTLP HTTP exporter → {endpoint}")
            return exporter
        except ImportError:
            log.warning("OTLP exporter not installed: pip install opentelemetry-exporter-otlp")
            return _setup_sqlite(config)

def _setup_langfuse(config: dict) -> Any:
    """Langfuse exporter — best open-source LLM observability platform."""
    try:
        from langfuse import Langfuse
        public_key = config.get("public_key") or os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = config.get("secret_key") or os.environ.get("LANGFUSE_SECRET_KEY")
        host = config.get("host") or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

        if not public_key or not secret_key:
            log.warning("Langfuse keys not set. Set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY")
            return _setup_sqlite(config)

        langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        log.info(f"Langfuse exporter → {host}")

        # Create OTEL-compatible wrapper
        class LangfuseSpanExporter:
            """Wraps Langfuse SDK as an OTEL-compatible exporter."""
            def __init__(self, lf): self._lf = lf
            def export(self, spans):
                for span in spans:
                    attrs = dict(span.attributes or {})
                    trace = self._lf.trace(id=format(span.context.trace_id, '032x'),
                        name=span.name, metadata=attrs)
                    gen = trace.generation(name=span.name,
                        model=attrs.get("gen_ai.request.model", ""),
                        input=attrs.get("gen_ai.prompt", ""),
                        output=attrs.get("gen_ai.completion", ""),
                        usage={"input": int(attrs.get("gen_ai.usage.input_tokens", 0)),
                               "output": int(attrs.get("gen_ai.usage.output_tokens", 0))},
                        metadata=attrs)
                self._lf.flush()
            def shutdown(self): self._lf.flush()
            def force_flush(self, timeout=None): self._lf.flush()

        exporter = LangfuseSpanExporter(langfuse)
        _register(exporter)
        return exporter

    except ImportError:
        log.warning("Langfuse not installed: pip install langfuse")
        return _setup_sqlite(config)

def _setup_jaeger(config: dict) -> Any:
    """Jaeger exporter via OTLP."""
    endpoint = config.get("endpoint") or os.environ.get("JAEGER_ENDPOINT", "http://localhost:4317")
    return _setup_otlp({"endpoint": endpoint})

def _setup_console() -> Any:
    """Console exporter for debugging."""
    try:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        exporter = ConsoleSpanExporter()
        _register(exporter)
        return exporter
    except ImportError:
        return _setup_sqlite({})

def _setup_sqlite(config: dict) -> Any:
    """Default SQLite exporter (built-in, no deps)."""
    from largestack._observe.sqlite_exporter import SQLiteSpanExporter
    db_path = config.get("db_path") or os.path.expanduser("~/.largestack/traces.db")
    exporter = SQLiteSpanExporter(db_path)
    _register(exporter)
    return exporter

_REDACT_PATTERNS = [
    # Common secret-bearing keys
    ("authorization", "Bearer "), ("authorization", "Basic "),
    ("api-key", ""), ("x-api-key", ""), ("api_key", ""), ("apikey", ""),
    ("password", ""), ("secret", ""), ("token", ""),
]
_REDACT_VALUE_PREFIXES = ("sk-", "pk-", "xoxb-", "ghp_", "gho_", "Bearer ")
_REDACTED = "[REDACTED]"


def _redact_attr_value(key: str, value):
    """Redact secret-looking attributes. Conservative: only known patterns."""
    if not isinstance(value, str):
        return value
    klow = key.lower()
    # Header-style key match
    if klow in ("authorization", "api-key", "x-api-key", "api_key", "apikey",
                "password", "x-secret", "secret", "token", "x-auth-token"):
        return _REDACTED
    # Value pattern match (catches API keys leaked in arbitrary attrs)
    for prefix in _REDACT_VALUE_PREFIXES:
        if value.startswith(prefix):
            return _REDACTED
    return value


def _redacting_processor(inner_processor):
    """Wrap a span processor to redact sensitive attributes before export.
    
    v0.3.7.1: Subclasses opentelemetry SpanProcessor so the full protocol
    (on_start, on_end, _on_ending, shutdown, force_flush, etc.) is inherited
    rather than duck-typed. The previous duck-typed wrapper crashed when
    OTel SDK called _on_ending() (a private hook used by composite span
    processors), breaking live LLM calls when tracing was enabled.
    """
    try:
        from opentelemetry.sdk.trace import SpanProcessor
    except ImportError:
        # No OTel installed → return inner unchanged. Caller handles wrapping.
        return inner_processor

    class RedactingSpanProcessor(SpanProcessor):
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def on_start(self, span, parent_context=None):
            try:
                self._wrapped.on_start(span, parent_context)
            except Exception:
                pass

        def on_end(self, span):
            try:
                if hasattr(span, "_attributes") and span._attributes:
                    for k in list(span._attributes.keys()):
                        v = span._attributes[k]
                        new_v = _redact_attr_value(k, v)
                        if new_v != v:
                            span._attributes[k] = new_v
            except Exception:
                pass
            try:
                self._wrapped.on_end(span)
            except Exception:
                pass

        def _on_ending(self, span):
            """Forward _on_ending to inner processor if it implements it.
            
            This protocol method was added to opentelemetry-sdk for processor
            composition; not implementing it broke live LLM tracing.
            """
            try:
                inner_hook = getattr(self._wrapped, "_on_ending", None)
                if callable(inner_hook):
                    inner_hook(span)
            except Exception:
                pass

        def shutdown(self):
            try:
                self._wrapped.shutdown()
            except Exception:
                pass

        def force_flush(self, timeout_millis: int = 30000):
            try:
                return self._wrapped.force_flush(timeout_millis)
            except Exception:
                return False

    return RedactingSpanProcessor(inner_processor)


def _register(exporter):
    """Register exporter with the global TracerProvider, with secret redaction."""
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            if exporter.__class__.__name__ == "SQLiteSpanExporter":
                inner = SimpleSpanProcessor(exporter)
            else:
                inner = BatchSpanProcessor(exporter)
            # Wrap with redaction unless explicitly disabled
            if os.environ.get("LARGESTACK_OTEL_DISABLE_REDACTION", "").lower() not in ("1", "true", "yes"):
                provider.add_span_processor(_redacting_processor(inner))
            else:
                provider.add_span_processor(inner)
    except ImportError:
        pass
