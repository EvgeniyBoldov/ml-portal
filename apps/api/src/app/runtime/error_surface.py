from __future__ import annotations

import re
from typing import Optional


_INTERNAL_ERROR_PATTERNS = [
    r"\btraceback\b",
    r"\bexception\b",
    r"\bstack\s*trace\b",
    r"\berror_code\b",
    r"\bpreflight\b",
    r"\btool[_\s-]?call\b",
    r"\bsub[_\s-]?agent\b",
    r"\bruntime\b",
    r"\boperation[_\s-]?(unavailable|ambiguous|invalid)\b",
    r"\bagent[_\s-]?(runtime|precheck|wall[_\s-]?time|max[_\s-]?tool)\b",
]


def looks_internal_error_text(text: str) -> bool:
    sample = str(text or "").strip().lower()
    if not sample:
        return False
    return any(re.search(pattern, sample) for pattern in _INTERNAL_ERROR_PATTERNS)


def build_user_safe_error_message(
    *,
    retryable: Optional[bool],
    error_code: Optional[str],
) -> str:
    code = str(error_code or "").strip().lower()
    if retryable is True and code not in {
        "agent_precheck_failed",
        "agent_unavailable",
        "agent_no_operations",
        "operation_unavailable",
        "operation_ambiguous",
        "agent_non_retryable_operation_failure",
        "agent_required_operation_call_missing",
        "agent_max_tool_calls_exceeded",
        "agent_wall_time_exceeded",
    }:
        return (
            "Во время выполнения запроса возникли временные проблемы. "
            "Попробуйте повторить запрос позже. Если проблема повторится, сообщите ран-администратору."
        )
    return (
        "Во время выполнения запроса возникли проблемы. "
        "Сообщите ран-администратору."
    )
