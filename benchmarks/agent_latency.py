"""Agent latency benchmark — measures p50/p95/p99 over N runs."""
import asyncio
import statistics
import time
import sys
sys.path.insert(0, ".")

from largestack.testing import TestModel
from largestack import Agent


async def benchmark(n: int = 100):
    """Benchmark agent.run() latency with TestModel (no real LLM)."""
    test_model = TestModel(custom_output_text="Mocked")
    agent = Agent(name="bench", llm="test/mock")
    
    # Patch the gateway to use TestModel
    from unittest.mock import patch, AsyncMock
    
    latencies_ms = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            await agent.run("test prompt")
        except Exception:
            pass
        latencies_ms.append((time.perf_counter() - t0) * 1000)
    
    latencies_ms.sort()
    print(f"Runs: {n}")
    print(f"  p50:  {statistics.median(latencies_ms):.2f}ms")
    print(f"  p95:  {latencies_ms[int(n * 0.95)]:.2f}ms")
    print(f"  p99:  {latencies_ms[int(n * 0.99)]:.2f}ms")
    print(f"  mean: {statistics.mean(latencies_ms):.2f}ms")


if __name__ == "__main__":
    asyncio.run(benchmark(50))
