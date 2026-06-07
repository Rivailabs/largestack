"""Regression tests for issues caught during final verification of v0.3.7.

These tests exist to prevent two specific live-call breakages from recurring.
They run without external API access — they verify the structural properties
that the live tests would have validated.
"""

import sys

sys.path.insert(0, ".")


# ─── P0-VER-1: OTEL RedactingSpanProcessor must implement full SpanProcessor protocol ─


def test_redacting_span_processor_is_subclass_of_spanprocessor():
    """v0.3.7.1: RedactingSpanProcessor must subclass opentelemetry SpanProcessor
    so all protocol methods (on_start, on_end, _on_ending, shutdown, force_flush)
    are inherited. The previous duck-typed wrapper crashed when OTel SDK called
    _on_ending() during composite-processor span lifecycle handling.
    """
    try:
        from opentelemetry.sdk.trace import SpanProcessor
    except ImportError:
        import pytest

        pytest.skip("opentelemetry-sdk not installed")
    from largestack._observe.otel_export import _redacting_processor

    class FakeInner:
        def on_start(self, span, ctx=None):
            pass

        def on_end(self, span):
            pass

        def shutdown(self):
            pass

        def force_flush(self, t=30000):
            return True

    wrapped = _redacting_processor(FakeInner())
    assert isinstance(wrapped, SpanProcessor), (
        "RedactingSpanProcessor must be a SpanProcessor subclass to inherit "
        "all protocol methods incl. _on_ending"
    )
    # Must have the previously-missing _on_ending method
    assert hasattr(wrapped, "_on_ending"), "missing _on_ending hook"
    # Must not raise when called with a fake span
    fake_span = type("S", (), {})()
    wrapped._on_ending(fake_span)  # should not raise


def test_redacting_span_processor_forwards_on_ending_to_inner():
    """If inner processor implements _on_ending, the wrapper must call it."""
    try:
        from opentelemetry.sdk.trace import SpanProcessor
    except ImportError:
        import pytest

        pytest.skip("opentelemetry-sdk not installed")
    from largestack._observe.otel_export import _redacting_processor

    calls = []

    class FakeInner:
        def on_start(self, span, ctx=None):
            pass

        def on_end(self, span):
            pass

        def shutdown(self):
            pass

        def force_flush(self, t=30000):
            return True

        def _on_ending(self, span):
            calls.append("on_ending")

    wrapped = _redacting_processor(FakeInner())
    fake_span = type("S", (), {})()
    wrapped._on_ending(fake_span)
    assert calls == ["on_ending"], "wrapper must forward _on_ending to inner if available"


def test_redacting_span_processor_swallows_inner_on_ending_errors():
    """If inner._on_ending raises, wrapper must not propagate (defensive)."""
    try:
        from opentelemetry.sdk.trace import SpanProcessor
    except ImportError:
        import pytest

        pytest.skip("opentelemetry-sdk not installed")
    from largestack._observe.otel_export import _redacting_processor

    class FakeInner:
        def on_start(self, s, c=None):
            pass

        def on_end(self, s):
            pass

        def shutdown(self):
            pass

        def force_flush(self, t=30000):
            return True

        def _on_ending(self, s):
            raise RuntimeError("boom")

    wrapped = _redacting_processor(FakeInner())
    # Must not raise
    wrapped._on_ending(type("S", (), {})())


# ─── P0-VER-2: Per-run token accumulation reads input_tokens + output_tokens ─


def test_engine_per_run_accumulator_reads_input_and_output_tokens():
    """v0.3.7.1: AgentEngine.execute() must accumulate tokens from
    `resp.input_tokens + resp.output_tokens` (the actual LLMResponse fields),
    not from a non-existent `resp.tokens` attribute.
    """
    import inspect
    from largestack._core import engine as eng_mod

    src = inspect.getsource(eng_mod)
    # The accumulator must reference both fields
    assert "input_tokens" in src, "engine must read input_tokens from response"
    assert "output_tokens" in src, "engine must read output_tokens from response"


def test_llmresponse_has_input_and_output_token_fields():
    """Defensive: confirm the LLMResponse contract has the field names the
    engine relies on."""
    from largestack.types import LLMResponse

    fields = LLMResponse.model_fields
    assert "input_tokens" in fields
    assert "output_tokens" in fields


def test_engine_token_accumulator_works_with_real_response_shape():
    """Simulate a single LLMResponse and verify token accumulation works
    end-to-end without contacting a real provider.
    """
    import asyncio
    from largestack.types import LLMResponse
    from largestack._core.engine import AgentEngine
    from largestack._core.steering import SteeringResult, SteeringAction

    # Build a minimal fake gateway whose chat() returns a fixed response
    class FakeGateway:
        cost_tracker = type("CT", (), {"run_cost": 0.0, "run_tokens": 0})()

        async def chat(self, model, messages, tools=None, agent_name=None, **kw):
            return LLMResponse(
                content="four", model=model, input_tokens=10, output_tokens=5, cost=0.0001
            )

    class FakeSteering:
        async def run_after(self, resp, ctx):
            return SteeringResult(action=SteeringAction.PROCEED)

        async def run_before(self, tool, params, ctx):
            return SteeringResult(action=SteeringAction.PROCEED)

    class FakeRegistry:
        def get_all_schemas(self):
            return []

    class FakeToolExec:
        registry = FakeRegistry()
        perms = {}

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "openai/gpt-4o"
    eng.gateway = FakeGateway()
    eng.guardrails = None
    eng.memory = None
    eng.steering = FakeSteering()
    eng.tool_exec = FakeToolExec()
    eng.config = type("C", (), {"context_compression": False})()
    eng.max_turns = 1
    eng.cost_budget = 1.0
    eng.instructions = ""
    eng._compressor = None

    async def run():
        return await eng.execute("hi")

    result = asyncio.run(run())
    # Verify accumulator captured both input + output tokens
    assert result.total_tokens == 15, f"expected 15 (10+5), got {result.total_tokens}"
    assert abs(result.total_cost - 0.0001) < 1e-9
