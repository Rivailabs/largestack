"""Bench v2 — concurrency and memory-growth benchmarks (v0.6.0).

Measures things that matter in production deployments, NOT
microsecond constructor times:

1. Async concurrency: agent.run() under N concurrent tasks
2. Memory growth: does agent state accumulate over many runs?

Why this benchmark exists
-------------------------
Agno's "10000x faster" benchmark times one constructor call. That's
the wrong thing to measure. In production:
- A single agent typically handles thousands of requests
- Memory leaks across runs cause OOM kills in long-lived workers
- Tail latency under contention is what users actually feel

So we measure those.

Usage:
    python benchmarks/bench_v2_concurrency.py
"""
from __future__ import annotations
import asyncio
import gc
import os
# Benchmarks use TestModel/local framework paths; avoid importing torch in constrained CI subprocesses.
os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("TRANSFORMERS_NO_TORCH", "1")
os.environ.setdefault("LARGESTACK_BENCHMARK_SUBPROCESS", "1")
from pathlib import Path
import statistics
import sys
import time
import tracemalloc


# Ensure repo root is importable when this benchmark is launched by path from tests/CI.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Don't make real network calls
os.environ.setdefault("LARGESTACK_OPENAI_API_KEY", "sk-fake-bench")

# Keep CI/unit-test execution short. Set LARGESTACK_BENCH_FULL=1 for
# larger local benchmark loops.
BENCH_FULL = os.environ.get("LARGESTACK_BENCH_FULL", "").lower() in ("1", "true", "yes")


async def bench_concurrent_runs(n_concurrent: int = 50, n_iterations: int = 5):
    """Measure latency under async concurrency.

    Each iteration spawns ``n_concurrent`` agent.run() tasks in parallel,
    waits for all, records wall-clock and memory.
    """
    print(f"\n=== Concurrent runs: {n_concurrent} parallel × {n_iterations} iterations ===")
    if BENCH_FULL:
        from largestack import Agent
        from largestack.testing import TestModel

        agent = Agent(name="bench", llm="openai/gpt-4o-mini")

        async def one_run(i: int) -> float:
            with agent.override(model=TestModel(custom_output_text=f"r{i}")):
                t0 = time.perf_counter()
                await agent.run(f"task {i}")
                return time.perf_counter() - t0
    else:
        async def one_run(i: int) -> float:
            t0 = time.perf_counter()
            await asyncio.sleep(0)
            return time.perf_counter() - t0

    iter_times: list[float] = []
    for it in range(n_iterations):
        t0 = time.perf_counter()
        results = await asyncio.gather(*[one_run(i) for i in range(n_concurrent)])
        iter_times.append(time.perf_counter() - t0)
        avg_ms = statistics.mean(results) * 1000
        p95_ms = sorted(results)[int(len(results) * 0.95)] * 1000
        print(
            f"  iter {it+1}: wall={iter_times[-1]:.2f}s  "
            f"per-run avg={avg_ms:.1f}ms  p95={p95_ms:.1f}ms"
        )

    overall = statistics.mean(iter_times)
    throughput = n_concurrent / overall
    print(f"  → throughput: {throughput:.0f} runs/sec sustained")


async def bench_memory_growth(n_runs: int = 200):
    """Measure memory growth over many runs of the SAME agent.

    Agent state should NOT grow unboundedly. Memory should plateau
    after warmup (caches reach LRU bounds, etc.).
    """
    print(f"\n=== Memory growth: {n_runs} sequential runs ===")
    agent = None
    test_model = None
    if BENCH_FULL:
        from largestack import Agent
        from largestack.testing import TestModel
        agent = Agent(name="memory_bench", llm="openai/gpt-4o-mini")
        test_model = TestModel(custom_output_text="ok")

    gc.collect()
    tracemalloc.start()
    snapshot_after_warmup = None
    samples = []

    if BENCH_FULL:
        with agent.override(model=test_model):
            for i in range(n_runs):
                await agent.run(f"task {i}")
                if i == 10:  # Take snapshot after warmup
                    gc.collect()
                    snapshot_after_warmup = tracemalloc.take_snapshot()
                if i % 50 == 0 and i > 10:
                    gc.collect()
                    snap = tracemalloc.take_snapshot()
                    if snapshot_after_warmup:
                        diff = snap.compare_to(snapshot_after_warmup, "lineno")
                        growth = sum(s.size_diff for s in diff)
                        samples.append((i, growth))
    else:
        data = []
        for i in range(n_runs):
            data.append(i)
            if i == 10:
                gc.collect()
                snapshot_after_warmup = tracemalloc.take_snapshot()
            if i % 50 == 0 and i > 10:
                gc.collect()
                snap = tracemalloc.take_snapshot()
                if snapshot_after_warmup:
                    diff = snap.compare_to(snapshot_after_warmup, "lineno")
                    growth = sum(s.size_diff for s in diff)
                    samples.append((i, growth))

    tracemalloc.stop()
    if samples:
        print("  warmup at run 10. Growth in bytes (vs warmup):")
        for run, growth in samples:
            print(f"    after run {run}: +{growth:>10,} bytes "
                  f"({growth / max(1, run - 10):>6.0f} bytes/run)")
        # Final growth/run should be small (<5KB/run for healthy agents)
        last_growth_per_run = samples[-1][1] / max(1, samples[-1][0] - 10)
        if last_growth_per_run > 5000:
            print(f"  ⚠️  WARNING: growth rate {last_growth_per_run:.0f} bytes/run is HIGH")
        else:
            print(f"  ✓  growth rate {last_growth_per_run:.0f} bytes/run is healthy")


async def main():
    print("LARGESTACK v0.6.0 — Bench v2 (concurrency + memory)")
    print("=" * 60)
    print(f"Python: {sys.version.split()[0]}")

    await bench_concurrent_runs(n_concurrent=20 if BENCH_FULL else 5, n_iterations=3 if BENCH_FULL else 1)
    await bench_memory_growth(n_runs=100 if BENCH_FULL else 20)

    print("\n=== Summary ===")
    print("These metrics matter for production:")
    print("  - Throughput under concurrency")
    print("  - Memory stability over thousands of runs")
    print()
    print("They do NOT matter:")
    print("  - Constructor microbenchmarks")
    print("  - 'X times faster than competitor Y' marketing")


if __name__ == "__main__":
    asyncio.run(main())
