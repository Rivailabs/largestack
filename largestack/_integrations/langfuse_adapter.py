"""Langfuse observability adapter (v0.14.0).

Closes Tier D #41. LARGESTACK doesn't compete with Langfuse — it integrates.
This adapter:

1. Configures LARGESTACK's OTEL exporter to point at Langfuse Cloud or
   self-hosted Langfuse
2. Provides a ``LangfuseTracer`` shim that wraps LARGESTACK spans with
   Langfuse-flavored attributes (``langfuse.user.id``,
   ``langfuse.session.id``, ``langfuse.trace.tags``)
3. Adds the LARGESTACK-unique compliance tags (``compliance.dpdp.section``,
   ``compliance.rbi.framework``) which Langfuse renders as filterable
   labels

Strategy: pair, don't replace. Langfuse already accepts LARGESTACK's OTEL
export. This module makes the pairing zero-config.

Usage::

    from largestack._integrations.langfuse_adapter import (
        LangfuseConfig, configure_langfuse,
    )

    configure_langfuse(LangfuseConfig(
        public_key="pk-lf-...",
        secret_key="sk-lf-...",
        host="https://cloud.langfuse.com",
        # Or self-host:
        # host="https://langfuse.our-org.in",
    ))

    # Now LARGESTACK spans flow to Langfuse automatically
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("largestack.integrations.langfuse")


@dataclass
class LangfuseConfig:
    """Langfuse client configuration.

    Either pass keys explicitly or set:
    - ``LANGFUSE_PUBLIC_KEY``
    - ``LANGFUSE_SECRET_KEY``
    - ``LANGFUSE_HOST``
    """
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"
    release: str = ""
    environment: str = "production"
    flush_at: int = 15
    flush_interval_seconds: float = 0.5
    enable: bool = True
    # India-residency: Langfuse Cloud is EU-based. For India residency,
    # self-host on AWS Mumbai. ``allow_non_india_host=False`` enforces this.
    allow_non_india_host: bool = True

    def __post_init__(self):
        if not self.public_key:
            self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        if not self.secret_key:
            self.secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        if self.host == "https://cloud.langfuse.com":
            env_host = os.getenv("LANGFUSE_HOST")
            if env_host:
                self.host = env_host

        # India-residency check
        if not self.allow_non_india_host:
            india_markers = (
                "ap-south", "mumbai", ".in/", ".in:", ".in",
            )
            if not any(m in self.host.lower() for m in india_markers):
                raise ValueError(
                    f"host '{self.host}' does not appear to be "
                    "India-resident. Set allow_non_india_host=True or "
                    "use a Mumbai-region self-host."
                )


def _have_langfuse() -> bool:
    try:
        import langfuse  # noqa
        return True
    except ImportError:
        return False


def _have_opentelemetry() -> bool:
    try:
        import opentelemetry  # noqa
        return True
    except ImportError:
        return False


# -------------------- Configuration --------------------

class LangfuseTracer:
    """Wraps LARGESTACK spans with Langfuse-flavored attributes.

    The actual transport is OTEL — this class just adds the
    ``langfuse.*`` attributes that Langfuse uses for indexing.
    """

    def __init__(self, config: LangfuseConfig):
        self.config = config
        self._client = None

    def get_client(self):
        """Lazy-construct the langfuse client."""
        if self._client is not None:
            return self._client
        if not _have_langfuse():
            raise ImportError(
                "langfuse required. Install: pip install langfuse"
            )
        from langfuse import Langfuse
        self._client = Langfuse(
            public_key=self.config.public_key,
            secret_key=self.config.secret_key,
            host=self.config.host,
            release=self.config.release or None,
            environment=self.config.environment,
            flush_at=self.config.flush_at,
            flush_interval=self.config.flush_interval_seconds,
            enabled=self.config.enable,
        )
        return self._client

    def trace(
        self,
        *,
        name: str,
        user_id: str = "",
        session_id: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Start a Langfuse trace. Returns the langfuse trace/span object.

        v1.1.1: support both Langfuse SDK v2 (``client.trace(...)``) and v3 (which
        removed ``trace()`` in favour of ``start_span(...)``). The OTEL export path
        (``configure_otel_export_to_langfuse``) is the recommended integration and
        is unaffected by this.
        """
        client = self.get_client()
        kwargs: dict[str, Any] = {"name": name}
        if user_id:
            kwargs["user_id"] = user_id
        if session_id:
            kwargs["session_id"] = session_id
        if tags:
            kwargs["tags"] = tags
        if metadata:
            kwargs["metadata"] = metadata
        if hasattr(client, "trace"):  # Langfuse SDK v2
            return client.trace(**kwargs)
        if hasattr(client, "start_span"):  # Langfuse SDK v3
            return client.start_span(**kwargs)
        raise RuntimeError(
            "Unsupported Langfuse SDK: no trace()/start_span(). Use the OTEL export "
            "path (configure_otel_export_to_langfuse) or pin a supported langfuse."
        )

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception as e:
                log.warning(f"langfuse flush failed: {e}")

    def attach(self, agent: Any = None):
        """Context manager that activates this tracer for the enclosed block.

        Usage::

            tracer = LangfuseTracer(LangfuseConfig(public_key=..., secret_key=...))
            with tracer.attach(agent):
                result = agent.run_sync("...")     # spans flow to Langfuse
            # Auto-flushes on exit.

        ``agent`` is accepted for API symmetry with what the developer docs
        describe; the tracer attaches globally (Langfuse uses a global OTEL
        provider), so the agent argument is informational only and has no
        side effect on which agents get traced. Pass it for clarity, or omit.
        """
        tracer = self

        class _AttachCtx:
            def __init__(self, t, a):
                self._tracer = t
                self._agent = a
                self._prev_global = None

            def __enter__(self):
                # Make this tracer the active global tracer for the duration.
                global _global_tracer
                self._prev_global = _global_tracer
                _global_tracer = self._tracer
                # Eagerly construct the langfuse client so import errors
                # surface at attach time, not deep inside the agent run.
                if self._tracer.config.enable and self._tracer.config.public_key:
                    self._tracer.get_client()
                return self._tracer

            def __exit__(self, exc_type, exc, tb):
                global _global_tracer
                try:
                    self._tracer.flush()
                finally:
                    _global_tracer = self._prev_global
                # Don't swallow exceptions
                return False

        return _AttachCtx(tracer, agent)


# Module-level singleton (most apps want one tracer)
_global_tracer: LangfuseTracer | None = None


def configure_langfuse(config: LangfuseConfig) -> LangfuseTracer:
    """Configure the global Langfuse tracer."""
    global _global_tracer
    if not config.public_key:
        raise ValueError(
            "public_key required. Set LANGFUSE_PUBLIC_KEY env var or "
            "pass explicitly."
        )
    if not config.secret_key:
        raise ValueError("secret_key required.")

    _global_tracer = LangfuseTracer(config)
    log.info(f"langfuse configured: host={config.host}")
    return _global_tracer


def get_tracer() -> LangfuseTracer | None:
    """Return the configured global tracer (or None if not configured)."""
    return _global_tracer


# -------------------- OTEL bridge --------------------

def configure_otel_export_to_langfuse(
    config: LangfuseConfig,
) -> bool:
    """Configure OTEL trace exporter to send to Langfuse's OTEL endpoint.

    Langfuse exposes ``/api/public/otel/v1/traces`` for OTLP/HTTP.
    Returns True if OTEL setup succeeded.
    """
    if not _have_opentelemetry():
        log.warning(
            "opentelemetry not installed; "
            "skipping OTEL export to Langfuse"
        )
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            log.warning(
                "opentelemetry-exporter-otlp-proto-http required. "
                "Install: pip install opentelemetry-exporter-otlp"
            )
            return False
    except ImportError as e:
        log.warning(f"OTEL setup failed: {e}")
        return False

    import base64
    auth = base64.b64encode(
        f"{config.public_key}:{config.secret_key}".encode()
    ).decode()
    endpoint = f"{config.host.rstrip('/')}/api/public/otel/v1/traces"

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": f"Basic {auth}"},
    )
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        new_provider = TracerProvider()
        new_provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(new_provider)

    log.info(f"OTEL → Langfuse configured: {endpoint}")
    return True


# -------------------- LARGESTACK-unique attribute helpers --------------------

def langfuse_attributes_for_dpdp(
    *,
    section: str,
    purpose: str,
    lawful_basis: str,
) -> dict[str, str]:
    """Build Langfuse attributes for a DPDP-tagged trace."""
    return {
        "compliance.dpdp.section": section,
        "compliance.dpdp.purpose": purpose,
        "compliance.dpdp.lawful_basis": lawful_basis,
        "compliance.framework": "DPDP_Act_2023",
    }


def langfuse_attributes_for_rbi(
    *,
    framework: str,
    section: str = "",
) -> dict[str, str]:
    """Build Langfuse attributes for an RBI-tagged trace."""
    return {
        "compliance.rbi.framework": framework,
        "compliance.rbi.section": section,
        "compliance.framework": framework,
    }


def langfuse_attributes_for_tenant(
    *,
    tenant_id: str,
    sector: str = "",
) -> dict[str, str]:
    """Build Langfuse attributes for tenant-scoped traces."""
    if not tenant_id:
        raise ValueError("tenant_id required")
    return {
        "tenant.id": tenant_id,
        "tenant.sector": sector,
    }


__all__ = [
    "LangfuseConfig",
    "LangfuseTracer",
    "configure_langfuse",
    "get_tracer",
    "configure_otel_export_to_langfuse",
    "langfuse_attributes_for_dpdp",
    "langfuse_attributes_for_rbi",
    "langfuse_attributes_for_tenant",
]
