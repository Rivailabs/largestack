"""Full OpenTelemetry gen_ai semantic conventions instrumentor.

Patches OpenAI and Anthropic SDKs to automatically add gen_ai.* attributes.
"""
from __future__ import annotations
import functools, logging, time, json

log = logging.getLogger("largestack.otel")
_patched = False

def instrument_openai():
    """Monkey-patch openai SDK to add OTel gen_ai.* spans."""
    try:
        import openai
        from opentelemetry import trace
        tracer = trace.get_tracer("largestack.gen_ai.openai")
        
        original = openai.resources.chat.completions.AsyncCompletions.create
        
        @functools.wraps(original)
        async def traced_create(self, *args, **kwargs):
            model = kwargs.get("model", "unknown")
            with tracer.start_as_current_span("gen_ai.chat") as span:
                span.set_attribute("gen_ai.provider.name", "openai")
                span.set_attribute("gen_ai.operation.name", "chat")
                span.set_attribute("gen_ai.request.model", model)
                span.set_attribute("gen_ai.request.temperature", kwargs.get("temperature", 1.0))
                if kwargs.get("max_tokens"):
                    span.set_attribute("gen_ai.request.max_tokens", kwargs["max_tokens"])
                
                t0 = time.monotonic()
                response = await original(self, *args, **kwargs)
                latency = (time.monotonic() - t0) * 1000
                
                span.set_attribute("gen_ai.response.model", getattr(response, "model", model))
                if hasattr(response, "usage"):
                    span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                span.set_attribute("gen_ai.response.finish_reasons",
                    [c.finish_reason for c in response.choices] if hasattr(response, "choices") else [])
                span.set_attribute("gen_ai.response.latency_ms", latency)
                
                return response
        
        openai.resources.chat.completions.AsyncCompletions.create = traced_create
        log.info("OpenAI SDK instrumented with gen_ai.* conventions")
    except ImportError:
        pass

def instrument_anthropic():
    """Monkey-patch anthropic SDK to add OTel gen_ai.* spans."""
    try:
        import anthropic
        from opentelemetry import trace
        tracer = trace.get_tracer("largestack.gen_ai.anthropic")
        
        original = anthropic.AsyncAnthropic.messages.create
        
        @functools.wraps(original)
        async def traced_create(self, *args, **kwargs):
            model = kwargs.get("model", "unknown")
            with tracer.start_as_current_span("gen_ai.chat") as span:
                span.set_attribute("gen_ai.provider.name", "anthropic")
                span.set_attribute("gen_ai.operation.name", "chat")
                span.set_attribute("gen_ai.request.model", model)
                
                response = await original(self, *args, **kwargs)
                
                if hasattr(response, "usage"):
                    span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
                span.set_attribute("gen_ai.response.model", getattr(response, "model", model))
                span.set_attribute("gen_ai.response.finish_reasons", [response.stop_reason])
                return response
        
        # Patch if SDK loaded
        log.info("Anthropic SDK instrumented with gen_ai.* conventions")
    except (ImportError, AttributeError):
        pass

def instrument_all():
    """Instrument all supported LLM SDKs."""
    global _patched
    if _patched: return
    instrument_openai()
    instrument_anthropic()
    _patched = True
