#!/usr/bin/env python3
"""Load / throughput harness for the agent run loop.

HONEST SCOPE: by default this drives a deterministic TestModel, so it measures the
*framework's* per-run overhead and concurrency behaviour (guardrails, engine, tracing,
result assembly) — NOT a provider's latency. That's deliberate: it isolates what
largestack adds. For an end-to-end load test, point --llm at a real provider/local model.

A single short run here is NOT "load-proven" — soak/scale claims require sustained runs
on representative infra. This harness gives you the numbers; running it long enough to
matter is an ops exercise.

    python scripts/load_test.py --n 1000 --concurrency 50
    python scripts/load_test.py --n 200 --concurrency 10 --llm ollama/qwen2.5:0.5b
"""

from __future__ import annotations
import argparse, asyncio, time


async def _run_one(agent, task: str) -> tuple[bool, float]:
    t0 = time.perf_counter()
    try:
        await agent.run(task)
        return True, time.perf_counter() - t0
    except Exception:
        return False, time.perf_counter() - t0


async def main(n: int, concurrency: int, llm: str | None):
    from largestack import Agent

    agent = Agent(
        name="load", instructions="Reply briefly.", llm=llm, guardrails=["pii", "injection"]
    )
    use_test = llm is None
    ctx = None
    if use_test:
        from largestack.testing import TestModel

        ctx = agent.override(model=TestModel(custom_output_text="ok"))
        ctx.__enter__()
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    ok = 0

    async def _task(i):
        nonlocal ok
        async with sem:
            success, dt = await _run_one(agent, f"request {i}: summarize policy")
            latencies.append(dt)
            ok += int(success)

    t0 = time.perf_counter()
    await asyncio.gather(*[_task(i) for i in range(n)])
    wall = time.perf_counter() - t0
    if ctx:
        ctx.__exit__(None, None, None)
    await agent.aclose()

    latencies.sort()

    def pct(p):
        return (
            latencies[min(int(len(latencies) * p / 100), len(latencies) - 1)] if latencies else 0.0
        )

    print("LOAD TEST RESULT")
    print(f"  mode         : {'TestModel (framework overhead)' if use_test else llm}")
    print(f"  requests     : {n}  (concurrency {concurrency})")
    print(f"  success      : {ok}/{n}")
    print(f"  wall time    : {wall:.2f}s")
    print(f"  throughput   : {n / wall:.1f} req/s")
    print(f"  latency p50  : {pct(50) * 1000:.1f} ms")
    print(f"  latency p95  : {pct(95) * 1000:.1f} ms")
    print(f"  latency p99  : {pct(99) * 1000:.1f} ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--llm", default=None, help="real model id (else deterministic TestModel)")
    args = ap.parse_args()
    asyncio.run(main(args.n, args.concurrency, args.llm))
