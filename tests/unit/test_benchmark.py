"""Tests for benchmark runner."""
import asyncio, sys; sys.path.insert(0, ".")

def test_benchmark_runs():
    from largestack._test.benchmark import BenchmarkRunner
    runner = BenchmarkRunner(iterations=10, warmup=2)
    results = asyncio.run(runner.run_all())
    assert len(results) > 0
    for r in results:
        assert r.mean_ms > 0
        assert r.ops_per_sec > 0

def test_benchmark_result_stats():
    from largestack._test.benchmark import BenchmarkResult
    r = BenchmarkResult("test", [0.001, 0.002, 0.003, 0.001, 0.002], 5)
    assert r.mean_ms > 0
    assert r.median_ms > 0
    assert r.p95_ms >= r.median_ms
    assert r.ops_per_sec > 0

def test_benchmark_report():
    from largestack._test.benchmark import BenchmarkRunner
    import tempfile, os
    runner = BenchmarkRunner(iterations=5, warmup=1)
    asyncio.run(runner.run_all())
    path = os.path.join(tempfile.mkdtemp(), "bench.json")
    runner.save_report(path)
    assert os.path.exists(path)
