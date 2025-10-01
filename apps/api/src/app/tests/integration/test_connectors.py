import asyncio
from datetime import timedelta
import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.core.domain_exceptions import ExternalServiceCircuitBreakerOpen

def test_circuit_breaker_open_and_recovery():
    cb = CircuitBreaker("llm", CircuitBreakerConfig(failures_threshold=1, open_timeout_seconds=1.0))
    # First failure trips the breaker
    cb.on_failure()
    assert cb.state in ("open", "half_open", "OPEN", "HALF_OPEN")
    # Next call should be short-circuited
    with pytest.raises(ExternalServiceCircuitBreakerOpen):
        cb.before_call()
    # Fast-forward time safely
    cb._opened_at = cb._opened_at - 2.0  # emulate 2 seconds passed
    # Now should allow a trial call (HALF_OPEN)
    cb.before_call()
    # Simulate success -> closes
    cb.on_success()
    assert cb.state in ("closed", "CLOSED")

def test_circuit_breaker_half_open_exhaustion():
    cb = CircuitBreaker("emb", CircuitBreakerConfig(failures_threshold=1, open_timeout_seconds=0.1, half_open_max_calls=1))
    cb.on_failure()  # open
    with pytest.raises(ExternalServiceCircuitBreakerOpen):
        cb.before_call()  # still open
    # time passes
    cb._opened_at = cb._opened_at - 1.0
    cb.before_call()  # first trial ok
    with pytest.raises(ExternalServiceCircuitBreakerOpen):
        cb.before_call()  # second trial blocked by half_open_max_calls
