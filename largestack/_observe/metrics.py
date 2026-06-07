"""Prometheus-compatible metrics with O(1) bucket histograms (memory bounded by label cardinality)."""

from __future__ import annotations
import threading, logging
from collections import defaultdict

log = logging.getLogger("largestack.metrics")

DEFAULT_BUCKETS = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")]


class MetricsCollector:
    """Thread-safe metrics collector with bucket-counter histograms."""

    def __init__(self, buckets: list[float] = None):
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = defaultdict(float)
        self.buckets = buckets or DEFAULT_BUCKETS
        # Per-key: bucket counts (incremented at observe time → O(1) scrape)
        self._hist_buckets: dict[str, list[int]] = defaultdict(lambda: [0] * len(self.buckets))
        self._hist_count: dict[str, int] = defaultdict(int)
        self._hist_sum: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, labels: dict = None):
        with self._lock:
            self.counters[self._key(name, labels)] += value

    def set_gauge(self, name: str, value: float, labels: dict = None):
        with self._lock:
            self.gauges[self._key(name, labels)] = value

    def observe(self, name: str, value: float, labels: dict = None):
        """O(buckets) — increments bucket counters at observe time."""
        key = self._key(name, labels)
        with self._lock:
            buckets = self._hist_buckets[key]
            for i, b in enumerate(self.buckets):
                if value <= b:
                    buckets[i] += 1
            self._hist_count[key] += 1
            self._hist_sum[key] += value

    def format_prometheus(self) -> str:
        """O(metrics) scrape — no recompute over all samples."""
        with self._lock:
            counters = dict(self.counters)
            gauges = dict(self.gauges)
            hist_buckets = {k: list(v) for k, v in self._hist_buckets.items()}
            hist_count = dict(self._hist_count)
            hist_sum = dict(self._hist_sum)

        lines = []
        for k, v in sorted(counters.items()):
            lines.append(f"# TYPE {k.split('{')[0]} counter")
            lines.append(f"{k} {v}")
        for k, v in sorted(gauges.items()):
            lines.append(f"# TYPE {k.split('{')[0]} gauge")
            lines.append(f"{k} {v}")
        for k in sorted(hist_buckets.keys()):
            base = k.split("{")[0]
            label_part = k[len(base) :] if "{" in k else ""
            buckets = hist_buckets[k]
            lines.append(f"# TYPE {base} histogram")
            cumulative = 0
            for i, b in enumerate(self.buckets):
                cumulative += buckets[i]
                bl = "+Inf" if b == float("inf") else str(b)
                if label_part:
                    inner = label_part[1:-1]
                    lines.append(f'{base}_bucket{{{inner},le="{bl}"}} {cumulative}')
                else:
                    lines.append(f'{base}_bucket{{le="{bl}"}} {cumulative}')
            lines.append(f"{base}_count{label_part} {hist_count[k]}")
            lines.append(f"{base}_sum{label_part} {hist_sum[k]:.4f}")
        return "\n".join(lines)

    def _key(self, name: str, labels: dict = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    @property
    def histograms(self) -> dict:
        """Returns {key: {count, sum, buckets}} for each histogram."""
        with self._lock:
            return {
                k: {
                    "count": self._hist_count[k],
                    "sum": self._hist_sum[k],
                    "buckets": list(self._hist_buckets[k]),
                }
                for k in self._hist_count
            }


metrics = MetricsCollector()


def track_llm_call(model, tokens_in, tokens_out, cost, latency_ms):
    labels = {"model": model}
    metrics.inc("largestack_llm_requests_total", labels=labels)
    metrics.inc("largestack_llm_tokens_input_total", tokens_in, labels)
    metrics.inc("largestack_llm_tokens_output_total", tokens_out, labels)
    metrics.inc("largestack_llm_cost_total", cost, labels)
    metrics.observe("largestack_llm_latency_ms", latency_ms, labels)


def track_tool_call(tool_name, success, duration_ms):
    labels = {"tool": tool_name, "status": "ok" if success else "error"}
    metrics.inc("largestack_tool_calls_total", labels=labels)
    metrics.observe("largestack_tool_duration_ms", duration_ms, {"tool": tool_name})


def track_guardrail(guard_type, action):
    metrics.inc(
        "largestack_guardrail_triggers_total", labels={"type": guard_type, "action": action}
    )
