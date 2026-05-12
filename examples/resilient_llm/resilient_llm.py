"""Resilient LLM calls example.

Demonstrates the retry + circuit breaker patterns for production-grade
LLM and external API calls.

Real-world scenarios this handles:
- OpenAI rate limits (429) — retry with backoff
- Transient network errors — retry
- API outage — circuit breaker fails fast instead of cascading

Run::

    python resilient_llm.py
"""
from __future__ import annotations
import asyncio
import random

from largestack._core.resilience import (
    retry, CircuitBreaker, resilient, RetryError, CircuitOpenError,
)


# ============================================================
# Example 1: Plain retry decorator
# ============================================================

call_count = 0

@retry(
    max_attempts=5,
    initial_delay=0.1,
    max_delay=2.0,
    backoff_multiplier=2.0,
    jitter=True,
    retry_on=(RuntimeError,),
)
async def flaky_llm_call(prompt: str) -> str:
    """Simulates an LLM call that fails 60% of the time."""
    global call_count
    call_count += 1
    if random.random() < 0.6 and call_count < 4:
        raise RuntimeError(f"transient error on attempt {call_count}")
    return f"response to: {prompt}"


# ============================================================
# Example 2: Circuit breaker for an unstable downstream
# ============================================================

# A breaker shared across all calls to this provider
provider_breaker = CircuitBreaker(
    name="openai",
    failure_threshold=3,
    recovery_timeout=5.0,
)


async def call_provider(prompt: str) -> str:
    """Simulates a downstream that's currently degraded."""
    async with provider_breaker:
        # 80% failure rate to trigger the breaker quickly
        if random.random() < 0.8:
            raise RuntimeError("provider degraded")
        return f"provider response: {prompt}"


# ============================================================
# Example 3: Combined retry + breaker
# ============================================================

bedrock_breaker = CircuitBreaker(
    name="bedrock", failure_threshold=5, recovery_timeout=10.0,
)


@resilient(
    max_attempts=3,
    breaker=bedrock_breaker,
    retry_on=(RuntimeError,),
)
async def bedrock_invoke(prompt: str) -> str:
    """Production-grade Bedrock call with retry + breaker."""
    if random.random() < 0.3:
        raise RuntimeError("bedrock timeout")
    return f"bedrock: {prompt}"


# ============================================================
# Demo
# ============================================================

async def demo_retry():
    print("=" * 50)
    print("Example 1: Plain retry with backoff")
    print("=" * 50)
    global call_count
    call_count = 0
    try:
        result = await flaky_llm_call("Hello world")
        print(f"  ✓ Got: {result} (after {call_count} attempts)")
    except RetryError as e:
        print(f"  ✗ Failed after retries: {e}")
        print(f"  Last cause: {e.last_exception}")


async def demo_breaker():
    print("\n" + "=" * 50)
    print("Example 2: Circuit breaker")
    print("=" * 50)
    successes, failures, breaker_opens = 0, 0, 0
    for i in range(10):
        try:
            await call_provider(f"req{i}")
            successes += 1
        except CircuitOpenError:
            breaker_opens += 1
        except RuntimeError:
            failures += 1
    print(f"  successes: {successes}")
    print(f"  failures:  {failures}")
    print(f"  breaker open: {breaker_opens}")
    print(f"  breaker state: {provider_breaker.state}")


async def demo_combined():
    print("\n" + "=" * 50)
    print("Example 3: Combined retry + breaker")
    print("=" * 50)
    for i in range(5):
        try:
            result = await bedrock_invoke(f"call {i}")
            print(f"  [{i}] ✓ {result}")
        except (RetryError, CircuitOpenError) as e:
            print(f"  [{i}] ✗ {type(e).__name__}: {e}")


async def main():
    random.seed(42)  # deterministic for demo
    await demo_retry()
    await demo_breaker()
    await demo_combined()


if __name__ == "__main__":
    asyncio.run(main())
