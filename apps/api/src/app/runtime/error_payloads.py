from __future__ import annotations

import traceback
from typing import Any, Dict, Optional


def build_debug_payload(
    *,
    exc: BaseException | None = None,
    traceback_text: str | None = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any] | None:
    payload: Dict[str, Any] = {}
    if exc is not None:
        payload["exception_type"] = type(exc).__name__
    if traceback_text:
        payload["traceback"] = traceback_text
    elif exc is not None:
        formatted = traceback.format_exc()
        if formatted and formatted.strip() != "NoneType: None":
            payload["traceback"] = formatted
    if context:
        payload["context"] = dict(context)
    return payload or None


def build_error_metadata(
    *,
    error_code: str,
    retryable: bool,
    user_message: str,
    operator_message: str | None = None,
    source: str | None = None,
    debug: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error_code": error_code,
        "retryable": retryable,
        "user_message": user_message,
        "operator_message": operator_message or user_message,
    }
    if source:
        payload["source"] = source
    if debug:
        payload["debug"] = debug
    return payload
