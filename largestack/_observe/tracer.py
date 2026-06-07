"""Tracing setup — configurable backend via largestack.yaml trace_backend setting.

Backends: sqlite (default), langfuse, otlp, jaeger, console
"""

from __future__ import annotations
import os, logging

log = logging.getLogger("largestack.tracer")
_initialized = False


def setup_tracing(db_path: str = "~/.largestack/traces.db", backend: str = None):
    """Initialize tracing with configured backend."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "largestack-ai", "service.version": "0.1.1"})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        # Determine backend from config or param
        if backend is None:
            try:
                from largestack._core.config import get_config

                cfg = get_config()
                backend = cfg.trace_backend
            except Exception:
                backend = "sqlite"

        # Set up the exporter
        from largestack._observe.otel_export import setup_exporter

        if backend == "langfuse":
            try:
                from largestack._core.config import get_config

                cfg = get_config()
                setup_exporter(
                    "langfuse",
                    public_key=cfg.langfuse_public_key,
                    secret_key=cfg.langfuse_secret_key,
                    host=cfg.langfuse_host,
                )
            except Exception:
                setup_exporter("langfuse")  # Will read from env vars
        elif backend in ("otlp", "jaeger"):
            try:
                from largestack._core.config import get_config

                cfg = get_config()
                setup_exporter(backend, endpoint=cfg.otlp_endpoint)
            except Exception:
                setup_exporter(backend)
        elif backend == "console":
            setup_exporter("console")
        else:
            setup_exporter("sqlite", db_path=os.path.expanduser(db_path))

        # Auto-trace httpx
        try:
            from largestack._observe.auto_trace import patch_httpx

            patch_httpx()
        except Exception:
            pass

        log.info(f"Tracing initialized: backend={backend}")

    except ImportError:
        # OTel not installed — use SQLite-only fallback
        from largestack._observe.sqlite_exporter import SQLiteSpanExporter

        SQLiteSpanExporter(os.path.expanduser(db_path))
        log.debug("Tracing: SQLite-only (opentelemetry not installed)")
