"""
Backward-compatible shim.

Use `app.core.exceptions` as the source of truth for exception classes/handlers.
"""

from app.core.exceptions import (  # noqa: F401
    APIError,
    AppError,
    ExternalServiceError,
    CircuitBreakerOpen as ExternalServiceCircuitBreakerOpen,
    app_error_handler,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    install_exception_handlers,
)

