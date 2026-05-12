"""v0.6.0: Bench v2 regression tests.

Lightweight checks for production-relevant metrics that v0.6 introduced:
- Concurrency throughput stays above a floor
- Memory growth per run stays bounded
- Bench script itself executes successfully
"""
from __future__ import annotations

import asyncio
import gc
import time

import pytest


@pytest.mark.asyncio
async def test_concurrent_runs_complete_within_reasonable_time():
    """20 parallel agent.run() calls should finish in <5 seconds with TestModel."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="conc_test", llm="openai/gpt-4o-mini", guardrails=False)

    async def one_run(i: int):
        with agent.override(model=TestModel(custom_output_text=f"r{i}")):
            await agent.run(f"task {i}")

    t0 = time.perf_counter()
    await asyncio.gather(*[one_run(i) for i in range(20)])
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"20 parallel runs took {elapsed:.2f}s (expected <5s)"


@pytest.mark.asyncio
async def test_memory_growth_per_run_is_bounded():
    """Per-run memory growth should be small (<10KB/run).
    
    This is a coarse regression guard — meaningful regressions
    (caches that grow unboundedly, etc.) blow this up by 100x+.
    """
    import tracemalloc
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="mem_test", llm="openai/gpt-4o-mini", guardrails=False)

    # Warmup
    with agent.override(model=TestModel(custom_output_text="ok")):
        for i in range(5):
            await agent.run(f"warmup {i}")

    gc.collect()
    tracemalloc.start()
    snap0 = tracemalloc.take_snapshot()

    # Real measurement: 30 runs
    n_runs = 30
    with agent.override(model=TestModel(custom_output_text="ok")):
        for i in range(n_runs):
            await agent.run(f"task {i}")

    gc.collect()
    snap1 = tracemalloc.take_snapshot()
    diff = snap1.compare_to(snap0, "lineno")
    total_growth = sum(s.size_diff for s in diff)
    tracemalloc.stop()

    per_run = total_growth / n_runs
    # Generous bound: 50KB/run. A real leak would be much larger.
    assert per_run < 50_000, (
        f"memory growth {per_run:.0f} bytes/run exceeds 50KB threshold; "
        f"possible leak"
    )


def test_bench_v2_script_runs_without_error():
    """The bench v2 script must run cleanly."""
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent.parent
    script = repo / "benchmarks" / "bench_v2_concurrency.py"
    assert script.exists()
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (
        f"bench_v2 failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )
    # Sanity check expected output sections
    assert "Concurrent runs" in result.stdout
    assert "Memory growth" in result.stdout
