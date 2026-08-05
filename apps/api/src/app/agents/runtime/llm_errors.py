from __future__ import annotations

from typing import Any, Optional
from app.adapters.interfaces.llm import LLMErrorCode, LLMProviderError


class LLMToolCallingUnsupportedError(RuntimeError):
    """The provider/model cannot complete a native tool-calling request."""

    code = "llm_tool_calling_unsupported"
    retryable = False

    def __init__(self, message: str = "Native tool calling is not supported by the selected LLM") -> None:
        super().__init__(message)
        self.user_message = (
            "Выбранная модель не поддерживает вызов инструментов. "
            "Переключаюсь на текстовый протокол."
        )


class LLMRequestTooLargeError(RuntimeError):
    """The upstream provider rejected a request because its token budget is exceeded."""

    code = "llm_provider_request_too_large"
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = (
            "Запрос слишком большой для выбранной модели: превышен лимит контекста "
            "или токенов провайдера. Сократите задачу или разделите её на несколько шагов."
        )


def _error_body(exc: Exception) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    return body if isinstance(body, dict) else {}


def _error_text(exc: Exception) -> str:
    body = _error_body(exc)
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return " ".join(
        str(value)
        for value in (exc, error.get("message"), error.get("code"), error.get("type"))
        if value
    ).lower()


def is_tool_calling_unsupported_error(exc: Exception) -> bool:
    """Recognize only provider errors that justify plaintext fallback."""
    text = _error_text(exc)
    body = _error_body(exc)
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = str(error.get("code") or "").lower()
    return (
        code == "tool_use_failed"
        and ("tool choice is none" in text or "tool calling" in text)
    ) or any(
        marker in text
        for marker in (
            "tool calling is not supported",
            "tool_calls are not supported",
            "does not support tool calling",
            "unsupported tool calling",
            # vLLM rejects ``tool_choice=auto`` when the server was not
            # started with native tool-calling support and a parser.  This is
            # a capability mismatch, not an agent failure: the runtime can
            # continue with its textual tool_call protocol.
            "auto tool choice requires --enable-auto-tool-choice",
            "enable-auto-tool-choice and --tool-call-parser",
        )
    )


def is_request_too_large_error(exc: Exception) -> bool:
    text = _error_text(exc)
    return any(
        marker in text
        for marker in (
            "error code: 413",
            "request too large",
            "tokens per minute",
            "context_length_exceeded",
            "maximum context length",
        )
    )


def classify_provider_error(exc: Exception) -> Optional[RuntimeError]:
    if isinstance(exc, LLMProviderError):
        if exc.code is LLMErrorCode.TOOL_CALLING_UNSUPPORTED:
            return LLMToolCallingUnsupportedError(exc.safe_message)
        if exc.code is LLMErrorCode.REQUEST_TOO_LARGE:
            return LLMRequestTooLargeError(exc.safe_message)
        return exc
    if isinstance(exc, (LLMToolCallingUnsupportedError, LLMRequestTooLargeError)):
        return exc
    if is_tool_calling_unsupported_error(exc):
        return LLMToolCallingUnsupportedError(str(exc))
    if is_request_too_large_error(exc):
        return LLMRequestTooLargeError(str(exc))
    return None
