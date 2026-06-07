"""Async retry + circuit breaker utilities (v0.10.0).

Two production patterns every external API call needs:

1. ``retry`` — decorator and context manager for exponential-backoff retry
   with jitter, configurable backoff and max attempts, and selective
   exception handling. No external dep (no tenacity/backoff).

2. ``CircuitBreaker`` — open/half-open/closed state machine that prevents
   cascading failures when a downstream is misbehaving. Implements the
   classic Hystrix-style breaker.

Both are battle-tested patterns for any agent that calls flaky APIs
(LLMs, vector stores, third-party SDKs).
"""

from __future__ import annotations
import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

log = logging.getLogger("largestack.resilience")

T = TypeVar("T")


# -------------------- Retry --------------------


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: BaseException | None = None):
        super().__init__(message)
        self.last_exception = last_exception


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_attempts: int = 3  # total attempts including the first
    initial_delay: float = 0.5  # seconds before first retry
    max_delay: float = 30.0  # cap on backoff
    backoff_multiplier: float = 2.0  # exponential factor
    jitter: bool = True  # randomize ±50%
    retry_on: tuple = (Exception,)  # which exceptions trigger retry
    do_not_retry_on: tuple = ()  # exceptions that bypass retry

    def delay_for_attempt(self, attempt: int) -> float:
        """Compute backoff for attempt N (1-indexed)."""
        # attempt=1 means "before first retry" → use initial_delay
        delay = min(
            self.initial_delay * (self.backoff_multiplier ** (attempt - 1)),
            self.max_delay,
        )
        if self.jitter:
            delay *= 0.5 + random.random()
        return delay


def retry(
    max_attempts: int = 3,
    *,
    initial_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    retry_on: tuple = (Exception,),
    do_not_retry_on: tuple = (),
):
    """Async retry decorator with exponential backoff.

    Usage::

        @retry(max_attempts=5, retry_on=(httpx.HTTPError,))
        async def call_api():
            ...

    Or with a config::

        cfg = RetryConfig(max_attempts=5, initial_delay=1.0)
        @retry_with(cfg)
        async def call_api():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        backoff_multiplier=backoff_multiplier,
        jitter=jitter,
        retry_on=retry_on,
        do_not_retry_on=do_not_retry_on,
    )
    return retry_with(config)


def retry_with(config: RetryConfig):
    """Same as ``retry`` but takes a ``RetryConfig`` instance."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except config.do_not_retry_on:
                    # Don't retry these
                    raise
                except config.retry_on as e:
                    last_exc = e
                    if attempt >= config.max_attempts:
                        break
                    delay = config.delay_for_attempt(attempt)
                    log.debug(
                        f"{fn.__name__} attempt {attempt} failed: {e}; retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
            raise RetryError(
                f"{fn.__name__} failed after {config.max_attempts} attempts",
                last_exception=last_exc,
            )

        return wrapper

    return decorator


# -------------------- Circuit Breaker --------------------


class CircuitOpenError(Exception):
    """Raised when calling a circuit that is currently OPEN."""


@dataclass
class CircuitBreaker:
    """Hystrix-style circuit breaker.

    States:
    - CLOSED: requests pass through; failures are counted
    - OPEN: requests fail fast with CircuitOpenError
    - HALF_OPEN: one trial request after cooldown; success → CLOSED, fail → OPEN

    Args:
        failure_threshold: failures before opening
        recovery_timeout: seconds before transitioning OPEN → HALF_OPEN
        half_open_max_requests: how many trial calls in HALF_OPEN
        success_threshold: successes in HALF_OPEN to close

    Usage::

        cb = CircuitBreaker(name="openai", failure_threshold=5)

        async with cb:
            return await openai_call(...)

        # or as decorator
        @cb.protect
        async def openai_call(...): ...
    """

    name: str = "default"
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_requests: int = 1
    success_threshold: int = 1

    # State tracked dynamically (not in __init__ default hash)
    state: str = "CLOSED"
    failures: int = 0
    successes_in_half_open: int = 0
    half_open_attempts: int = 0
    last_failure_time: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    @property
    def is_half_open(self) -> bool:
        return self.state == "HALF_OPEN"

    @property
    def is_closed(self) -> bool:
        return self.state == "CLOSED"

    def _maybe_transition_to_half_open(self):
        if self.state != "OPEN":
            return
        if time.time() - self.last_failure_time >= self.recovery_timeout:
            log.info(f"breaker {self.name}: OPEN → HALF_OPEN")
            self.state = "HALF_OPEN"
            self.half_open_attempts = 0
            self.successes_in_half_open = 0

    def _allow(self) -> bool:
        """Whether to allow a call in current state."""
        self._maybe_transition_to_half_open()
        if self.state == "OPEN":
            return False
        if self.state == "HALF_OPEN":
            if self.half_open_attempts >= self.half_open_max_requests:
                return False
            self.half_open_attempts += 1
            return True
        return True

    def _on_success(self):
        if self.state == "HALF_OPEN":
            self.successes_in_half_open += 1
            if self.successes_in_half_open >= self.success_threshold:
                log.info(f"breaker {self.name}: HALF_OPEN → CLOSED")
                self.state = "CLOSED"
                self.failures = 0
                self.successes_in_half_open = 0
                self.half_open_attempts = 0
        elif self.state == "CLOSED":
            self.failures = 0  # reset on success

    def _on_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.state == "HALF_OPEN":
            log.warning(f"breaker {self.name}: HALF_OPEN → OPEN")
            self.state = "OPEN"
            self.successes_in_half_open = 0
            self.half_open_attempts = 0
        elif self.state == "CLOSED" and self.failures >= self.failure_threshold:
            log.warning(
                f"breaker {self.name}: CLOSED → OPEN ({self.failures} consecutive failures)"
            )
            self.state = "OPEN"

    async def __aenter__(self):
        if not self._allow():
            raise CircuitOpenError(f"breaker {self.name!r} is OPEN — failing fast")
        return self

    async def __aexit__(self, exc_type, exc_val, tb):
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure()
        return False  # don't swallow

    def protect(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator that wraps an async function with this breaker."""

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with self:
                return await fn(*args, **kwargs)

        return wrapper

    def reset(self):
        """Force the breaker back to CLOSED state."""
        self.state = "CLOSED"
        self.failures = 0
        self.successes_in_half_open = 0
        self.half_open_attempts = 0
        self.last_failure_time = 0.0


# -------------------- Combined: retry + circuit breaker --------------------


def resilient(
    *,
    max_attempts: int = 3,
    breaker: CircuitBreaker | None = None,
    retry_on: tuple = (Exception,),
):
    """Combine retry + circuit breaker in one decorator.

    Trips breaker on persistent failure, retries within breaker.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            cfg = RetryConfig(max_attempts=max_attempts, retry_on=retry_on)
            last_exc: BaseException | None = None
            for attempt in range(1, cfg.max_attempts + 1):
                if breaker is not None and not breaker._allow():
                    raise CircuitOpenError(f"breaker {breaker.name!r} is OPEN")
                try:
                    result = await fn(*args, **kwargs)
                    if breaker is not None:
                        breaker._on_success()
                    return result
                except retry_on as e:
                    last_exc = e
                    if breaker is not None:
                        breaker._on_failure()
                    if attempt >= cfg.max_attempts:
                        break
                    await asyncio.sleep(cfg.delay_for_attempt(attempt))
            raise RetryError(
                f"{fn.__name__} failed after {cfg.max_attempts} attempts",
                last_exception=last_exc,
            )

        return wrapper

    return decorator
