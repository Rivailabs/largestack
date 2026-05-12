"""Tests for agent health monitoring."""
import sys; sys.path.insert(0, ".")
from largestack._core.health import AgentMonitor, AgentHealth

def test_health_initial():
    h = AgentHealth("test")
    assert h.status == "idle" and h.error_rate == 0

def test_health_after_success():
    h = AgentHealth("test")
    h.record_success(0.01, 100)
    assert h.status == "healthy" and h.total_runs == 1

def test_health_degraded():
    h = AgentHealth("test")
    for _ in range(8): h.record_success(0.01, 100)
    for _ in range(2): h.record_failure("timeout")
    assert h.status == "degraded"  # 20% error rate

def test_health_unhealthy():
    h = AgentHealth("test")
    for _ in range(10): h.record_failure("crash")
    assert h.status == "unhealthy"

def test_monitor_multiple():
    mon = AgentMonitor()
    mon.record("a1", True, 0.01, 100)
    mon.record("a2", False, 0, 0, "fail")
    all_health = mon.check_all()
    assert all_health["a1"]["status"] == "healthy"
    assert all_health["a2"]["status"] == "unhealthy"
    assert mon.unhealthy_agents() == ["a2"]

def test_health_quality_tracking():
    from largestack._core.health import AgentHealth
    h = AgentHealth("test")
    h.record_success(0.01, 100, quality_score=0.9)
    h.record_success(0.01, 100, quality_score=0.8)
    assert h.avg_quality > 0.8

def test_health_silent_failure():
    from largestack._core.health import AgentHealth
    h = AgentHealth("test")
    for _ in range(10):
        h.record_success(0.01, 100, quality_score=0.1)  # Low quality
    assert h.silent_failure_rate > 0.5
    assert h.status == "degraded"
