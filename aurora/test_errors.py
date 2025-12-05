"""Unit tests for Aurora error handling utilities."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from aurora.utils.errors import CircuitBreaker, RetryConfig, retry_with_backoff


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_failure_threshold(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)

        # First two failures - still closed
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

        # Third failure - opens
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        """Test successful execution resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        cb.record_success()
        assert cb.failure_count == 0

        # Now need 3 more failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_transitions_to_half_open_after_timeout(self):
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        # Simulate time passing
        cb.last_failure_time = datetime.now() - timedelta(seconds=2)

        # Should transition to half-open
        assert cb.can_execute() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_allows_limited_attempts(self):
        """Test half-open state allows limited attempts."""
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=0.1, half_open_attempts=3
        )

        # Open and wait for half-open
        cb.record_failure()
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)

        # First call transitions to half-open and allows execution
        assert cb.can_execute() is True
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.half_open_count == 1

        # Should allow more attempts up to the limit
        assert cb.can_execute() is True
        assert cb.half_open_count == 2
        assert cb.can_execute() is True
        assert cb.half_open_count == 3

        # Should block after exhausting attempts
        assert cb.can_execute() is False

    def test_half_open_closes_on_success(self):
        """Test half-open transitions to closed on success."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Open and wait for half-open
        cb.record_failure()
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)
        cb.can_execute()  # Transition to half-open

        assert cb.state == CircuitBreaker.HALF_OPEN

        # Success should close the circuit
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0

    def test_half_open_reopens_after_exhausting_attempts(self):
        """Test half-open re-opens after all attempts fail."""
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=0.1, half_open_attempts=2
        )

        # Open and wait for half-open
        cb.record_failure()
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)

        # Transition to half-open
        assert cb.can_execute() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

        # First failure - should stay half-open (attempt 1 of 2)
        cb.record_failure()
        assert cb.state == CircuitBreaker.HALF_OPEN

        # Allow second attempt
        assert cb.can_execute() is True

        # Second failure - should re-open (exhausted attempts)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_half_open_stays_open_until_attempts_exhausted(self):
        """Test half-open doesn't immediately re-open on first failure."""
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=0.1, half_open_attempts=3
        )

        # Open and wait for half-open
        cb.record_failure()
        cb.record_failure()
        cb.last_failure_time = datetime.now() - timedelta(seconds=1)

        # Transition to half-open
        cb.can_execute()
        assert cb.state == CircuitBreaker.HALF_OPEN

        # Multiple failures should be tolerated
        cb.record_failure()
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.can_execute()

        cb.record_failure()
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.can_execute()

        # Third failure exhausts attempts
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Test function succeeds on first try."""
        mock_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)

        result = await retry_with_backoff(mock_func, config)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Test function retries on failure."""
        mock_func = AsyncMock(
            side_effect=[Exception("fail"), Exception("fail"), "success"]
        )
        config = RetryConfig(max_attempts=3, base_delay=0.01)

        result = await retry_with_backoff(mock_func, config)

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Test raises exception after exhausting retries."""
        mock_func = AsyncMock(side_effect=Exception("persistent failure"))
        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(Exception, match="persistent failure"):
            await retry_with_backoff(mock_func, config)

        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_respects_circuit_breaker(self):
        """Test respects circuit breaker state."""
        mock_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)
        cb = CircuitBreaker(failure_threshold=1)

        # Open the circuit
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        with pytest.raises(Exception, match="Circuit breaker is open"):
            await retry_with_backoff(mock_func, config, cb)

        # Function should not have been called
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_records_success_to_circuit_breaker(self):
        """Test records success to circuit breaker."""
        mock_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)
        cb = CircuitBreaker(failure_threshold=3)

        # Add some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        await retry_with_backoff(mock_func, config, cb)

        # Success should reset failure count
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_records_failures_to_circuit_breaker(self):
        """Test records failures to circuit breaker."""
        mock_func = AsyncMock(side_effect=Exception("fail"))
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        cb = CircuitBreaker(failure_threshold=5)

        with pytest.raises(Exception):
            await retry_with_backoff(mock_func, config, cb)

        # Should have recorded 2 failures
        assert cb.failure_count == 2
