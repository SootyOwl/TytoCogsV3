"""Error handling and recovery utilities for Aurora event system."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Awaitable
from functools import wraps

log = logging.getLogger("red.tyto.aurora.errors")


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered, limited requests allowed

    This class is thread-safe and can be used from multiple async tasks.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_attempts: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            half_open_attempts: Number of attempts allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_attempts = half_open_attempts

        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_count = 0
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """Check if execution is allowed in current state."""
        async with self._lock:
            if self.state == self.CLOSED:
                return True

            if self.state == self.OPEN:
                # Check if recovery timeout has elapsed
                if self.last_failure_time:
                    elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                    if elapsed >= self.recovery_timeout:
                        log.info("Circuit breaker entering half-open state")
                        self.state = self.HALF_OPEN
                        self.half_open_count = 1  # Count this as the first attempt
                        return True
                return False

            if self.state == self.HALF_OPEN:
                # Allow limited attempts
                if self.half_open_count < self.half_open_attempts:
                    self.half_open_count += 1
                    return True
                return False

            return False

    async def record_success(self):
        """Record successful execution."""
        async with self._lock:
            if self.state == self.HALF_OPEN:
                log.info("Circuit breaker closing after successful recovery")
                self.state = self.CLOSED
                self.failure_count = 0
                self.half_open_count = 0
            elif self.state == self.CLOSED:
                # Reset failure count on success
                self.failure_count = 0

    async def record_failure(self):
        """Record failed execution."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == self.HALF_OPEN:
                # Only re-open if we've exhausted all half-open attempts
                if self.half_open_count >= self.half_open_attempts:
                    log.warning(
                        f"Circuit breaker re-opening after {self.half_open_count} failed "
                        f"recovery attempts"
                    )
                    self.state = self.OPEN
                    self.half_open_count = 0
                else:
                    log.info(
                        f"Half-open attempt {self.half_open_count}/{self.half_open_attempts} "
                        f"failed, will retry"
                    )
            elif self.state == self.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    log.error(
                        f"Circuit breaker opening after {self.failure_count} failures. "
                        f"Will retry in {self.recovery_timeout}s"
                    )
                    self.state = self.OPEN

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat()
            if self.last_failure_time
            else None,
            "next_retry": (
                (
                    self.last_failure_time + timedelta(seconds=self.recovery_timeout)
                ).isoformat()
                if self.state == self.OPEN and self.last_failure_time
                else None
            ),
        }


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        exponential_base: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ):
        """Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            exponential_base: Base for exponential backoff
            max_delay: Maximum delay between retries
            jitter: Add random jitter to delays
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.exponential_base = exponential_base
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        import random

        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add ±25% jitter
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)


async def retry_with_backoff(
    func: Callable[[], Awaitable[Any]],
    config: RetryConfig,
    circuit_breaker: Optional[CircuitBreaker] = None,
    before_retry: Optional[Callable[[int, Exception], Awaitable[None]]] = None,
) -> Any:
    """Execute function with retry logic and exponential backoff.

    Args:
        func: Async function to execute (use a closure or functools.partial to pass arguments)
        config: Retry configuration
        circuit_breaker: Optional circuit breaker to check
        before_retry: Optional async callback invoked after a failure but before the next attempt

    Returns:
        Result of successful function execution

    Raises:
        Exception: Last exception if all retries exhausted
    """
    last_exception = None

    for attempt in range(config.max_attempts):
        # Check circuit breaker
        if circuit_breaker and not await circuit_breaker.can_execute():
            raise Exception("Circuit breaker is open, execution blocked")

        try:
            result = await func()

            # Success - record and return
            if circuit_breaker:
                await circuit_breaker.record_success()

            if attempt > 0:
                log.info(f"Retry succeeded on attempt {attempt + 1}")

            return result

        except Exception as e:
            last_exception = e

            # Record failure
            if circuit_breaker:
                await circuit_breaker.record_failure()

            # Allow caller to perform cleanup before deciding on next attempt
            if before_retry:
                try:
                    await before_retry(attempt, e)
                except Exception as cleanup_err:
                    log.error(
                        "Error during retry cleanup after attempt %d: %s",
                        attempt + 1,
                        cleanup_err,
                    )

            # Check if this is the last attempt
            if attempt == config.max_attempts - 1:
                log.error(f"All {config.max_attempts} retry attempts exhausted")
                break

            # Calculate delay and log
            delay = config.get_delay(attempt)
            log.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed: {str(e)}. "
                f"Retrying in {delay:.2f}s..."
            )

            await asyncio.sleep(delay)

    # All retries exhausted
    if last_exception:
        raise last_exception
    # Should never reach here, but satisfy type checker
    raise RuntimeError("Retry loop exited unexpectedly")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
):
    """Decorator to add retry logic to async functions.

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Initial delay in seconds
        exponential_base: Base for exponential backoff

    Example:
        @with_retry(max_attempts=3, base_delay=2.0)
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                exponential_base=exponential_base,
            )
            # Create closure that captures args/kwargs
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                config,
            )

        return wrapper

    return decorator


class ErrorStats:
    """Track error statistics for monitoring and alerting.

    This class is thread-safe and can be used from multiple async tasks.
    """

    def __init__(self, window_size: int = 100):
        """Initialize error statistics tracker.

        Args:
            window_size: Number of recent operations to track
        """
        self.window_size = window_size
        self.recent_operations: deque[tuple[datetime, bool]] = deque(maxlen=window_size)
        self.error_counts: dict[str, int] = {}
        self.total_errors = 0
        self.total_operations = 0
        self._lock = asyncio.Lock()

    async def record_success(self):
        """Record successful operation."""
        async with self._lock:
            self._add_operation(True)

    async def record_error(self, error: Exception):
        """Record failed operation."""
        async with self._lock:
            self._add_operation(False)

            error_type = type(error).__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
            self.total_errors += 1

    def _add_operation(self, success: bool):
        """Add operation to tracking window. Internal use only - caller must hold lock."""
        self.recent_operations.append((datetime.now(), success))
        self.total_operations += 1
        # No need to manually maintain window size - deque handles it with maxlen

    async def get_error_rate(
        self, time_window_seconds: Optional[float] = None
    ) -> float:
        """Calculate error rate.

        Args:
            time_window_seconds: Optional time window for calculation

        Returns:
            Error rate as percentage (0-100)
        """
        async with self._lock:
            return self._get_error_rate_unlocked(time_window_seconds)

    def _get_error_rate_unlocked(
        self, time_window_seconds: Optional[float] = None
    ) -> float:
        """Calculate error rate. Internal use only - caller must hold lock."""
        if not self.recent_operations:
            return 0.0

        operations = list(self.recent_operations)

        if time_window_seconds:
            cutoff = datetime.now() - timedelta(seconds=time_window_seconds)
            operations = [(ts, success) for ts, success in operations if ts > cutoff]

        if not operations:
            return 0.0

        failures = sum(1 for _, success in operations if not success)
        return (failures / len(operations)) * 100

    async def get_stats(self) -> dict:
        """Get comprehensive error statistics."""
        async with self._lock:
            return {
                "total_operations": self.total_operations,
                "total_errors": self.total_errors,
                "recent_error_rate": self._get_error_rate_unlocked(),
                "error_rate_5min": self._get_error_rate_unlocked(300),
                "error_by_type": dict(self.error_counts),
                "window_size": len(self.recent_operations),
            }

    async def should_alert(self, threshold: float = 50.0) -> bool:
        """Check if error rate exceeds alert threshold.

        Args:
            threshold: Error rate percentage threshold (0-100)

        Returns:
            True if alert should be triggered
        """
        return await self.get_error_rate(300) > threshold  # 5 minute window
