"""Tests for circuit breaker."""

import sys, time

sys.path.insert(0, ".")
from largestack._core.circuit_breaker import CircuitBreaker, CircuitState


def test_initial_closed():
    cb = CircuitBreaker("test")
    assert cb.state == CircuitState.CLOSED and cb.allow_request()


def test_opens_after_failures():
    cb = CircuitBreaker("test", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN and not cb.allow_request()


def test_resets_on_success():
    cb = CircuitBreaker("test", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # Reset counter
    cb.record_failure()  # Only 1 failure now
    assert cb.state == CircuitState.CLOSED


def test_half_open_after_timeout():
    cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN and cb.allow_request()


def test_half_open_to_closed():
    cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_reset():
    cb = CircuitBreaker("test", failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
