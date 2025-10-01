class ExternalServiceError(RuntimeError):
    """Base class for domain-level external service errors."""

class ExternalServiceCircuitBreakerOpen(ExternalServiceError):
    """Raised when a circuit breaker is open and the call must be short-circuited."""
