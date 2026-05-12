"""Canary deployment — gradual rollout with multi-metric monitoring and auto-rollback."""
from __future__ import annotations
import logging, math, random, time
from collections import deque
from typing import Any

log = logging.getLogger("largestack.canary")


class CanaryDeployment:
    """Progressive rollout with statistical safety checks.
    
    Pattern: 1% → 5% → 10% → 25% → 50% → 100%
    
    Auto-advances when new version shows:
      - Success rate >= threshold
      - Latency not significantly worse than baseline
      - Minimum sample size for statistical confidence
    
    Auto-rollback on:
      - Success rate drop below floor
      - Latency regression beyond threshold
      - Error burst (recent errors exceed threshold)
    
    Usage:
        canary = CanaryDeployment(
            stages=[0.01, 0.05, 0.10, 0.25, 0.50, 1.0],
            success_rate_threshold=0.95,
            min_samples_per_stage=100,
        )
        
        if canary.should_use_new():
            result = new_version.run(...)
            canary.record_result("new", success=result.ok, latency_ms=result.latency)
        else:
            result = old_version.run(...)
            canary.record_result("old", ...)
        
        if canary.should_advance():
            canary.advance()
        if canary.should_rollback():
            canary.rollback()
    """
    def __init__(self,
                 stages: list[float] = None,
                 success_rate_threshold: float = 0.95,
                 rollback_threshold: float = 0.85,
                 latency_regression_factor: float = 1.5,
                 min_samples_per_stage: int = 10,
                 recent_window: int = 50):
        self.stages = stages or [0.01, 0.05, 0.10, 0.25, 0.50, 1.0]
        self.success_rate_threshold = success_rate_threshold
        self.rollback_threshold = rollback_threshold
        self.latency_regression_factor = latency_regression_factor
        self.min_samples_per_stage = min_samples_per_stage
        self.recent_window = recent_window
        
        self._current_stage = 0
        self._started = time.time()
        self._stage_started = time.time()
        
        # Per-version metrics
        self._metrics: dict[str, dict] = {
            "old": {"success": [], "latency": deque(maxlen=recent_window), "errors": []},
            "new": {"success": [], "latency": deque(maxlen=recent_window), "errors": []},
        }
        
        # Stage history for audit
        self._stage_history: list[dict] = []
    
    def should_use_new(self) -> bool:
        """Decide whether current request should hit the new version."""
        if self._current_stage >= len(self.stages):
            return True
        return random.random() < self.stages[self._current_stage]
    
    def record_result(self, version: str, success: bool,
                      latency_ms: float = 0, error_type: str = None):
        """Record a request outcome for monitoring."""
        if version not in self._metrics:
            return
        m = self._metrics[version]
        m["success"].append(1.0 if success else 0.0)
        m["latency"].append(latency_ms)
        if not success and error_type:
            m["errors"].append({"type": error_type, "time": time.time()})
    
    def _success_rate(self, version: str, window: int = None) -> float:
        samples = self._metrics[version]["success"]
        if window:
            samples = samples[-window:]
        if not samples:
            return 1.0
        return sum(samples) / len(samples)
    
    def _avg_latency(self, version: str) -> float:
        lat = self._metrics[version]["latency"]
        if not lat:
            return 0.0
        return sum(lat) / len(lat)
    
    def _recent_error_count(self, version: str, window_sec: float = 60) -> int:
        now = time.time()
        errors = self._metrics[version]["errors"]
        return sum(1 for e in errors if now - e["time"] < window_sec)
    
    def should_advance(self) -> bool:
        """Check if it's safe to advance to the next stage."""
        if self._current_stage >= len(self.stages) - 1:
            return False  # Already at 100%
        
        new_samples = len(self._metrics["new"]["success"])
        if new_samples < self.min_samples_per_stage:
            return False  # Not enough data
        
        # Check new version success rate
        new_sr = self._success_rate("new", window=self.recent_window)
        if new_sr < self.success_rate_threshold:
            return False
        
        # Check latency regression (if we have baseline)
        old_samples = len(self._metrics["old"]["success"])
        if old_samples > 10:
            old_lat = self._avg_latency("old")
            new_lat = self._avg_latency("new")
            if old_lat > 0 and new_lat > old_lat * self.latency_regression_factor:
                return False  # Too slow
        
        return True
    
    def should_rollback(self) -> bool:
        """Check if metrics indicate we should rollback."""
        new_samples = len(self._metrics["new"]["success"])
        if new_samples < 20:
            return False  # Not enough data yet
        
        # Check recent success rate
        new_sr = self._success_rate("new", window=self.recent_window)
        if new_sr < self.rollback_threshold:
            return True
        
        # Error burst: >5 errors in last 60s
        if self._recent_error_count("new", window_sec=60) > 5:
            return True
        
        return False
    
    def advance(self) -> bool:
        """Advance to next stage. Returns True if advanced."""
        if not self.should_advance():
            return False
        
        old_stage = self._current_stage
        self._current_stage += 1
        
        self._stage_history.append({
            "from_stage": old_stage,
            "to_stage": self._current_stage,
            "timestamp": time.time(),
            "new_success_rate": self._success_rate("new"),
            "new_avg_latency_ms": self._avg_latency("new"),
            "duration_seconds": time.time() - self._stage_started,
        })
        
        self._stage_started = time.time()
        log.info(
            f"Canary: advanced to stage {self._current_stage+1}/{len(self.stages)} "
            f"({self.current_percentage*100:.1f}%)"
        )
        return True
    
    def rollback(self):
        """Rollback to 0% new version."""
        self._stage_history.append({
            "rollback": True,
            "from_stage": self._current_stage,
            "timestamp": time.time(),
            "final_success_rate": self._success_rate("new"),
        })
        self._current_stage = 0
        # Clear new version metrics (starting fresh)
        self._metrics["new"] = {"success": [], "latency": deque(maxlen=self.recent_window), "errors": []}
        log.warning("Canary: rolled back to 0%")
    
    def force_complete(self):
        """Force promotion to 100% regardless of metrics (emergency)."""
        self._current_stage = len(self.stages) - 1
        self._stage_history.append({
            "forced": True, "timestamp": time.time(),
        })
        log.warning("Canary: forced to 100%")
    
    @property
    def current_percentage(self) -> float:
        if self._current_stage >= len(self.stages):
            return 1.0
        return self.stages[self._current_stage]
    
    @property
    def status(self) -> str:
        return f"Stage {self._current_stage+1}/{len(self.stages)} ({self.current_percentage*100:.1f}%)"
    
    @property
    def stats(self) -> dict:
        return {
            "current_stage": self._current_stage,
            "current_percentage": self.current_percentage,
            "total_stages": len(self.stages),
            "old_version": {
                "samples": len(self._metrics["old"]["success"]),
                "success_rate": self._success_rate("old"),
                "avg_latency_ms": self._avg_latency("old"),
            },
            "new_version": {
                "samples": len(self._metrics["new"]["success"]),
                "success_rate": self._success_rate("new"),
                "avg_latency_ms": self._avg_latency("new"),
                "recent_errors_60s": self._recent_error_count("new"),
            },
            "stage_history": self._stage_history,
            "should_advance": self.should_advance(),
            "should_rollback": self.should_rollback(),
        }
