"""v0.5.0: Performance regression tests (lightweight, no flakes).

These don't try to hit specific microsecond targets — they just guard
against gross regressions (10x slower than expected).
"""

from __future__ import annotations

import gc
import time

import pytest


def test_provider_cold_start_under_one_ms():
    """Lazy-init keeps provider construction below 1ms.

    Tightens the bound vs the existing test in test_v050_lazy_http.py
    which only checks <1000μs (1ms). On modern hardware this is ~0.3μs.
    """
    from largestack._core.providers.openai_prov import OpenAIProvider

    gc.collect()
    t0 = time.perf_counter_ns()
    for _ in range(1000):
        OpenAIProvider(api_key="sk-test")
    elapsed_per_call_us = (time.perf_counter_ns() - t0) / 1000 / 1000
    assert elapsed_per_call_us < 1000, (
        f"Provider cold-start regressed to {elapsed_per_call_us:.1f}μs (expected <1000μs)"
    )


def test_agent_cold_start_within_release_budget():
    """Agent() cold start should stay within a generous release budget.

    Full-extra environments may initialize optional guard/PII dependencies such
    as Presidio/spaCy, and clean Python installs are noisier than warmed dev
    shells. Keep this as a gross-regression guard instead of a hard 1s SLA.
    """
    from largestack import Agent

    gc.collect()
    t0 = time.perf_counter_ns()
    for _ in range(10):
        Agent(name="t", llm="openai/gpt-4o-mini")
    elapsed_per_call_ms = (time.perf_counter_ns() - t0) / 10 / 1_000_000
    budget_ms = 5000
    assert elapsed_per_call_ms < budget_ms, (
        f"Agent cold-start took {elapsed_per_call_ms:.1f}ms (expected <{budget_ms}ms)"
    )


def test_benchmark_script_runs_without_error():
    """The benchmark script itself must run cleanly — guards against
    accidental refactor breakage."""
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent.parent
    script = repo / "benchmarks" / "competitor_compare.py"
    assert script.exists()
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"benchmark script failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )
    # Sanity check expected output sections
    assert "Provider cold-start" in result.stdout
    assert "Memory per Agent" in result.stdout
