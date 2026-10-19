"""Safe model failure contracts shared by callbacks and extraction stages."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from pydantic import ValidationError


class ModelRequestError(RuntimeError):
    def __init__(self, message: str, *, code: str, retryable: bool, retry_after_seconds: float = 0) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = max(0, retry_after_seconds)


def http_failure(response: httpx.Response) -> ModelRequestError:
    # Only accept the safe callback contract; never persist raw upstream bodies,
    # request headers, prompts, or provider exception strings.
    try:
        detail = response.json().get("detail", {})
    except (ValueError, AttributeError):
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    delay = 0.0
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                pass
    return ModelRequestError(detail.get("message") or f"Model callback HTTP {response.status_code}",
        code=detail.get("code") or f"model_http_{response.status_code}",
        retryable=detail.get("retryable", response.status_code in {408, 429} or response.status_code >= 500),
        retry_after_seconds=max(delay, float(detail.get("retry_after_ms") or 0) / 1000))


def model_failure(exc: Exception) -> ModelRequestError:
    if isinstance(exc, ModelRequestError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        return http_failure(exc.response)
    if isinstance(exc, httpx.TimeoutException):
        return ModelRequestError("LLM request timeout", code="llm_timeout", retryable=True)
    if isinstance(exc, httpx.TransportError):
        return ModelRequestError("LLM connection failed", code="llm_connection_error", retryable=True)
    if isinstance(exc, (ValidationError, ValueError, KeyError, IndexError, TypeError)):
        return ModelRequestError("Invalid structured LLM response", code="llm_invalid_output", retryable=True)
    return ModelRequestError(f"LLM request failed ({type(exc).__name__})", code="llm_unknown_error", retryable=True)
