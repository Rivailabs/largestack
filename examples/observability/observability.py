"""OpenTelemetry observability example.

Shows how to instrument a LARGESTACK app with OTEL tracing. Spans show up
in Jaeger / Tempo / Honeycomb / Datadog.

Run::

    pip install opentelemetry-api opentelemetry-sdk \\
                opentelemetry-exporter-otlp-proto-grpc

    # Start a local OTEL collector (Jaeger has one built in)
    docker run -d --name jaeger -p 16686:16686 -p 4317:4317 \\
        jaegertracing/all-in-one:latest

    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
    python observability.py

    # Then open http://localhost:16686 to see traces
"""

from __future__ import annotations
import asyncio
import os

from largestack._observability.otel import (
    setup_otel,
    trace_span,
    trace_llm_call,
    trace_tool_call,
    start_span,
)


@trace_span("kyc.verify_pan")
async def verify_pan(pan: str) -> bool:
    """Each call shows up as a span in your tracing UI."""
    await asyncio.sleep(0.05)  # simulate API latency
    # Format check
    return len(pan) == 10


@trace_span("rag.retrieve")
async def retrieve(query: str, k: int = 5) -> list[dict]:
    async with start_span("vector_search", {"k": k}) as span:
        await asyncio.sleep(0.02)
        results = [{"id": f"doc{i}", "score": 1.0 - i * 0.1} for i in range(k)]
        span.set_attribute("largestack.rag.hits", len(results))
        return results


async def call_llm(model: str, prompt: str) -> str:
    """Shows the trace_llm_call helper for standardized LLM spans."""
    async with trace_llm_call(
        provider="openai",
        model=model,
        tenant_id="demo-tenant",
        prompt_tokens=len(prompt) // 4,
    ) as span:
        await asyncio.sleep(0.1)  # simulate LLM call
        completion = f"[{model}] response to {prompt[:30]}..."
        span.set_attribute("largestack.llm.completion_tokens", len(completion) // 4)
        return completion


async def use_tool(tool_name: str, args: str) -> str:
    """Shows the trace_tool_call helper."""
    async with trace_tool_call(
        tool_name=tool_name,
        tenant_id="demo-tenant",
    ):
        await asyncio.sleep(0.03)
        return f"{tool_name}({args}) → ok"


async def main():
    # Initialize OTEL — works as no-op if endpoint not set or SDK missing
    initialized = setup_otel(
        service_name="largestack-demo",
        sample_rate=1.0,  # trace everything in dev
    )

    if initialized:
        print("✓ OTEL initialized — traces will be exported to OTLP endpoint")
    else:
        print("⚠ OTEL not initialized (no endpoint or SDK missing)")
        print("  Spans will be no-ops. Code below still runs normally.")

    print("\nRunning a few traced operations...")

    # Each of these creates a span (or no-op if OTEL not set up)
    pan_valid = await verify_pan("AAACR1234C")
    print(f"  PAN valid: {pan_valid}")

    results = await retrieve("test query", k=5)
    print(f"  Retrieved {len(results)} docs")

    answer = await call_llm("gpt-4o-mini", "What is RAG?")
    print(f"  LLM: {answer}")

    tool_result = await use_tool("razorpay_create_payment_link", "₹100")
    print(f"  Tool: {tool_result}")

    print("\n✓ Done. Check your tracing UI to see the spans.")


if __name__ == "__main__":
    asyncio.run(main())
