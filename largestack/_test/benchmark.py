"""Benchmark suite — generate LARGESTACK's own performance numbers.

Covers:
  - Guardrail latency (PII, injection, toxicity, hallucination)
  - Memory operations (add, search, graph traversal)
  - Orchestration overhead (sequential, parallel, swarm)
  - RAG pipeline (chunking, retrieval, reranking)
  - Encryption/security operations
  - Dashboard and observability

Usage:
    runner = BenchmarkRunner()
    results = await runner.run_all()
    runner.save_report("benchmarks/results.json")
    runner.print_report()
"""

from __future__ import annotations
import asyncio, json, logging, os, time, statistics
from typing import Any, Callable

log = logging.getLogger("largestack.benchmark")


class BenchmarkResult:
    """Single benchmark result with statistics."""

    def __init__(self, name: str, times: list[float], iterations: int):
        self.name = name
        self.times = times
        self.iterations = iterations

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times) * 1000

    @property
    def median_ms(self) -> float:
        return statistics.median(self.times) * 1000

    @property
    def p95_ms(self) -> float:
        idx = min(int(len(self.times) * 0.95), len(self.times) - 1)
        return sorted(self.times)[idx] * 1000

    @property
    def p99_ms(self) -> float:
        idx = min(int(len(self.times) * 0.99), len(self.times) - 1)
        return sorted(self.times)[idx] * 1000

    @property
    def ops_per_sec(self) -> float:
        mean = statistics.mean(self.times)
        return 1.0 / mean if mean > 0 else 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "mean_ms": round(self.mean_ms, 3),
            "median_ms": round(self.median_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "ops_per_sec": round(self.ops_per_sec, 1),
            "min_ms": round(min(self.times) * 1000, 3),
            "max_ms": round(max(self.times) * 1000, 3),
        }


class BenchmarkRunner:
    """Run LARGESTACK benchmark suite."""

    def __init__(self, iterations: int = 100, warmup: int = 5):
        self.iterations = iterations
        self.warmup = warmup
        self.results: list[BenchmarkResult] = []

    def _bench_sync(self, name: str, fn: Callable, iterations: int = None) -> BenchmarkResult:
        iters = iterations or self.iterations
        # Warmup
        for _ in range(self.warmup):
            fn()
        # Measure
        times = []
        for _ in range(iters):
            start = time.perf_counter()
            fn()
            times.append(time.perf_counter() - start)
        result = BenchmarkResult(name, times, iters)
        self.results.append(result)
        return result

    async def _bench_async(
        self, name: str, fn: Callable, iterations: int = None
    ) -> BenchmarkResult:
        iters = iterations or self.iterations
        for _ in range(self.warmup):
            await fn()
        times = []
        for _ in range(iters):
            start = time.perf_counter()
            await fn()
            times.append(time.perf_counter() - start)
        result = BenchmarkResult(name, times, iters)
        self.results.append(result)
        return result

    async def run_all(self) -> list[BenchmarkResult]:
        """Run all benchmark categories."""
        self.results = []

        await self.bench_guardrails()
        await self.bench_memory()
        await self.bench_rag()
        self.bench_encryption()
        self.bench_anomaly()

        return self.results

    async def bench_guardrails(self):
        """Benchmark guardrail checks."""
        from largestack._guard.pii import PIIGuard
        from largestack._guard.injection import InjectionGuard
        from largestack._guard.toxicity import ToxicityGuard

        pii = PIIGuard()
        inj = InjectionGuard()
        tox = ToxicityGuard()

        test_text = "Hello, my email is john@example.com and SSN is 123-45-6789. Please help me with my account."

        self._bench_sync("guardrail/pii_redact", lambda: pii.redact(test_text))

        class MockMsg:
            def __init__(self):
                pass

        msgs = [{"role": "user", "content": test_text}]

        await self._bench_async("guardrail/injection_check", lambda: inj.check_input(msgs))

        class MockResp:
            content = "Normal safe response about programming"

        await self._bench_async("guardrail/toxicity_check", lambda: tox.check_output(MockResp()))

    async def bench_memory(self):
        """Benchmark memory operations."""
        from largestack._memory.buffer import ConversationMemory
        from largestack._memory.semantic import SemanticMemory
        from largestack._memory.graph import GraphMemory

        # Buffer
        buf = ConversationMemory(strategy="sliding", max_messages=100)
        msg = {"role": "user", "content": "Test message content"}
        await self._bench_async("memory/buffer_add", lambda: buf.add_message(msg))

        # Semantic
        sem = SemanticMemory()
        await sem.add("Python is a programming language")
        await sem.add("JavaScript runs in browsers")
        await sem.add("Rust is memory safe")
        await self._bench_async(
            "memory/semantic_search", lambda: sem.search("programming language", k=2)
        )

        # Graph
        g = GraphMemory()
        await g.add_entity("A", "node")
        await g.add_entity("B", "node")
        await g.add_entity("C", "node")
        await g.add_relation("A", "B", "knows")
        await g.add_relation("B", "C", "knows")
        await self._bench_async("memory/graph_query", lambda: g.query("A", depth=2))
        await self._bench_async("memory/graph_shortest_path", lambda: g.shortest_path("A", "C"))

    async def bench_rag(self):
        """Benchmark RAG components."""
        from largestack._rag.chunker import Chunker
        from largestack._rag.reranker import Reranker

        text = "This is a test document. " * 200
        chunker = Chunker(chunk_size=100)

        self._bench_sync("rag/chunking", lambda: chunker.chunk(text), iterations=50)

        reranker = Reranker(mode="keyword")
        docs = [{"text": f"Document about topic {i} with details"} for i in range(20)]
        self._bench_sync(
            "rag/reranking_20docs",
            lambda: reranker.rerank("topic 5 details", docs, top_k=5),
            iterations=50,
        )

    def bench_encryption(self):
        """Benchmark encryption operations."""
        from largestack._security.encryption import EncryptionManager

        enc = EncryptionManager(key="benchmark-key-32-chars-padding!!")
        plaintext = "Sensitive data that needs encryption" * 10

        self._bench_sync("security/encrypt", lambda: enc.encrypt(plaintext))

        ct = enc.encrypt(plaintext)
        self._bench_sync("security/decrypt", lambda: enc.decrypt(ct))

        self._bench_sync("security/hmac_sign", lambda: enc.hmac_sign(plaintext))

        self._bench_sync("security/hash_sha256", lambda: EncryptionManager.hash_sha256(plaintext))

    def bench_anomaly(self):
        """Benchmark anomaly detection."""
        from largestack._observe.anomaly import AnomalyDetector

        detector = AnomalyDetector(window=100)
        import random

        # Pre-fill
        for _ in range(50):
            detector.check(random.gauss(100, 10))

        self._bench_sync("observe/anomaly_check", lambda: detector.check(random.gauss(100, 10)))

    def save_report(self, path: str):
        """Save benchmark results to JSON."""
        report = {
            "largestack_version": "0.1.1",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "iterations": self.iterations,
            "results": [r.to_dict() for r in self.results],
        }
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)

    def print_report(self):
        """Print formatted benchmark report."""
        print(f"\n{'=' * 70}")
        print("  Largestack AI v0.1.1 — Benchmark Results")
        print(f"  Iterations: {self.iterations} | Warmup: {self.warmup}")
        print(f"{'=' * 70}")
        print(f"{'Benchmark':<35} {'Mean':>8} {'P95':>8} {'P99':>8} {'ops/s':>10}")
        print(f"{'-' * 70}")
        for r in self.results:
            print(
                f"{r.name:<35} {r.mean_ms:>7.2f}ms {r.p95_ms:>7.2f}ms {r.p99_ms:>7.2f}ms {r.ops_per_sec:>9.0f}"
            )
        print(f"{'=' * 70}\n")
