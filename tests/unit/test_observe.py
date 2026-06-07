"""Tests for observability."""

from largestack._observe.anomaly import AnomalyDetector
from largestack._observe.metrics import MetricsCollector, track_llm_call
from largestack._observe.event_replay import EventRecorder, EventReplayer


def test_anomaly_baseline():
    d = AnomalyDetector()
    import random

    random.seed(42)
    for _ in range(30):
        d.check(1.0 + random.uniform(-0.2, 0.2))  # Varying baseline
    r = d.check(1.15)  # Within normal range
    assert not r["is_anomaly"]


def test_anomaly_spike():
    d = AnomalyDetector()
    for _ in range(30):
        d.check(1.0)
    r = d.check(100.0)  # Major spike
    assert len(r["detectors"]) > 0  # At least 1 detector fires


def test_metrics():
    m = MetricsCollector()
    m.inc("requests", 1.0, {"model": "gpt-4o"})
    m.inc("requests", 1.0, {"model": "gpt-4o"})
    m.observe("latency", 150.0, {"model": "gpt-4o"})
    output = m.format_prometheus()
    assert "requests" in output
    assert "latency" in output


def test_track_llm():
    track_llm_call("gpt-4o", 1000, 500, 0.01, 150.0)
    from largestack._observe.metrics import metrics

    output = metrics.format_prometheus()
    assert "largestack_llm" in output


def test_event_recorder():
    rec = EventRecorder()
    rec.start()
    rec.record("llm.call", {"model": "gpt-4o", "tokens": 100})
    rec.record("tool.call", {"tool": "search"})
    events = rec.stop()
    assert len(events) == 2
    assert events[0]["type"] == "llm.call"


def test_event_replayer():
    events = [
        {"type": "start", "data": {}, "offset_ms": 0},
        {"type": "llm", "data": {"model": "gpt"}, "offset_ms": 100},
    ]
    replayer = EventReplayer(events=events)
    assert len(replayer.get_events("llm")) == 1
    assert len(replayer.get_events()) == 2
