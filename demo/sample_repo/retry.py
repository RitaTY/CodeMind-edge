"""
retry.py — Retry utilities with exponential backoff and jitter.

Provides a decorator and a standalone helper for retrying
flaky operations (HTTP calls, DB queries, external APIs).
"""

import functools
import logging
import random
import time
from typing import Callable, Type, Tuple, Any

logger = logging.getLogger(__name__)




def retry_with_exponential_backoff(
    func: Callable,
    *,
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Any:
    """
    Execute *func* with exponential backoff on failure.

    Delay formula:
        delay = min(base_delay * 2^attempt, max_delay)
        if jitter: delay += random.uniform(0, delay * 0.2)

    Args:
        func                — callable to retry (called with no args)
        max_attempts        — total number of attempts before giving up
        base_delay          — initial delay in seconds
        max_delay           — ceiling on delay
        jitter              — add randomness to avoid thundering herd
        retryable_exceptions — only catch these exception types

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception if all attempts are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()

        except retryable_exceptions as exc:
            last_exc = exc

            if attempt == max_attempts:
                logger.error(
                    "All %d retry attempts exhausted. Last error: %s",
                    max_attempts, exc,
                )
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                delay += random.uniform(0, delay * 0.2)

            logger.warning(
                "Attempt %d/%d failed (%s). Retrying in %.2fs…",
                attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]




def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator that retries a function on failure with exponential backoff.

    Usage:
        @retry(max_attempts=5, base_delay=0.5, retryable_exceptions=(IOError,))
        def fetch_data(url: str) -> dict:
            ...

        @retry()
        def unreliable_service_call():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return retry_with_exponential_backoff(
                lambda: func(*args, **kwargs),
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                retryable_exceptions=retryable_exceptions,
            )
        return wrapper
    return decorator




def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Async version of the retry decorator.

    Usage:
        @async_retry(max_attempts=5)
        async def call_external_api():
            ...
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except retryable_exceptions as exc:
                    last_exc = exc

                    if attempt == max_attempts:
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        delay += random.uniform(0, delay * 0.2)

                    logger.warning(
                        "[async] Attempt %d/%d failed (%s). Retrying in %.2fs…",
                        attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)

            raise last_exc  # type: ignore[misc]

        return wrapper
    return decorator




class CircuitBreaker:
    """
    Simple circuit breaker to stop hammering a failing service.

    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)

    Usage:
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

        def call():
            with cb:
                return external_service.get(...)
    """

    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self._failures         = 0
        self._state            = self.CLOSED
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed >= self.recovery_timeout:
                self._state = self.HALF_OPEN
        return self._state

    def __enter__(self):
        if self.state == self.OPEN:
            raise RuntimeError("Circuit breaker is OPEN — service unavailable")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Success — reset
            self._failures = 0
            self._state    = self.CLOSED
        else:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state    = self.OPEN
                self._opened_at = time.monotonic()
                logger.error(
                    "Circuit breaker tripped after %d failures.",
                    self._failures,
                )
        return False  # do not suppress exceptions
