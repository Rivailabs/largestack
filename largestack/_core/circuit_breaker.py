"""Circuit breaker — prevent cascading failures across providers.

States: CLOSED (normal) → OPEN (failing, reject fast) → HALF_OPEN (test one request)
Trips after `failure_threshold` consecutive failures.
Resets after `recovery_timeout` seconds.
"""

from __future__ import annotations
import time, logging
from enum import Enum

log = logging.getLogger("largestack.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# HTTP status codes that should NOT trip the circuit breaker
# 400 = bad request (user error), 401 = auth (config error), 404 = not found
# Only 429 (rate limit), 500, 502, 503, 504 (server errors) should trip it
TRIPPABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._success_count = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                log.info(f"Circuit '{self.name}' → HALF_OPEN (testing)")
        return self._state

    def allow_request(self) -> bool:
        """Check if request should be allowed through."""
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN:
            return True  # Allow one test request
        return False  # OPEN — reject fast

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            log.info(f"Circuit '{self.name}' → CLOSED (recovered)")
        self._success_count += 1
        self._failure_count = 0

    def record_failure(self, error=None):
        """Record failure. Only trips on server/rate-limit errors, not client errors."""
        # Check if this error should trip the breaker
        if error:
            status = getattr(error, "status_code", None) or getattr(error, "code", None)
            if status and isinstance(status, int) and status < 429:
                return  # Client error (400, 401, 404) — don't trip
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            log.warning(f"Circuit '{self.name}' → OPEN after {self._failure_count} failures")

    def reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def __repr__(self):
        return f"CircuitBreaker(name={self.name}, state={self.state.value}, failures={self._failure_count})"
