from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional
from app.core.domain_exceptions import ExternalServiceCircuitBreakerOpen

class CircuitBreakerState(str):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerConfig:
    failures_threshold: int = 5
    open_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1

class CircuitBreaker:
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.cfg = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        if self._state == CircuitBreakerState.OPEN and self._opened_at is not None:
            if time.time() - self._opened_at >= self.cfg.open_timeout_seconds:
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def _trip(self) -> None:
        self._state = CircuitBreakerState.OPEN
        self._opened_at = time.time()
        self._failures = 0
        self._half_open_calls = 0

    def before_call(self) -> None:
        s = self.state
        if s == CircuitBreakerState.OPEN:
            raise ExternalServiceCircuitBreakerOpen(f"Circuit '{self.name}' is open")
        if s == CircuitBreakerState.HALF_OPEN:
            if self._half_open_calls >= self.cfg.half_open_max_calls:
                raise ExternalServiceCircuitBreakerOpen(f"Circuit '{self.name}' is half-open")
            self._half_open_calls += 1

    def on_success(self) -> None:
        self._failures = 0
        self._half_open_calls = 0
        self._state = CircuitBreakerState.CLOSED
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._trip()
            return
        if self._failures >= self.cfg.failures_threshold:
            self._trip()
