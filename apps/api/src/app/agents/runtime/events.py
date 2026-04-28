"""
Runtime events — типы событий, которые runtime стримит наружу.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.runtime.operation_errors import RuntimeErrorCode


class RuntimeEventType(str, Enum):
    """Типы событий runtime"""
    STATUS = "status"
    THINKING = "thinking"
    OPERATION_CALL = "operation_call"
    OPERATION_RESULT = "operation_result"
    DELTA = "delta"
    FINAL = "final"
    ERROR = "error"
    # Planner loop events
    PLANNER_ACTION = "planner_action"
    POLICY_DECISION = "policy_decision"
    CONFIRMATION_REQUIRED = "confirmation_required"
    WAITING_INPUT = "waiting_input"
    STOP = "stop"


@dataclass
class RuntimeEvent:
    """
    Событие от AgentRuntime.
    Используется для стриминга прогресса выполнения.
    """
    type: RuntimeEventType
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def status(cls, stage: str, **extra: Any) -> RuntimeEvent:
        return cls(RuntimeEventType.STATUS, {"stage": stage, **extra})

    @classmethod
    def thinking(cls, step: int) -> RuntimeEvent:
        return cls(RuntimeEventType.THINKING, {"step": step})

    @classmethod
    def operation_call(
        cls,
        operation_slug: str,
        call_id: str,
        arguments: dict,
    ) -> RuntimeEvent:
        return cls(RuntimeEventType.OPERATION_CALL, {
            "operation": operation_slug,
            "call_id": call_id,
            "arguments": arguments,
        })

    @classmethod
    def operation_result(
        cls,
        operation_slug: str,
        call_id: str,
        success: bool,
        data: Any,
        *,
        reused: Optional[bool] = None,
        reused_from_call_id: Optional[str] = None,
        error_code: Optional[RuntimeErrorCode | str] = None,
        retryable: Optional[bool] = None,
        safe_message: Optional[str] = None,
        envelope: Optional[Dict[str, Any]] = None,
        truncated: Optional[bool] = None,
    ) -> RuntimeEvent:
        payload: Dict[str, Any] = {
            "operation": operation_slug,
            "call_id": call_id,
            "success": success,
            "data": data,
        }
        if error_code is not None:
            payload["error_code"] = (
                error_code.value if isinstance(error_code, RuntimeErrorCode) else str(error_code)
            )
        if reused is not None:
            payload["reused"] = bool(reused)
        if reused_from_call_id is not None:
            payload["reused_from_call_id"] = str(reused_from_call_id)
        if retryable is not None:
            payload["retryable"] = bool(retryable)
        if safe_message is not None:
            payload["safe_message"] = safe_message
        if envelope is not None:
            payload["result"] = dict(envelope)
        if truncated:
            payload["truncated"] = True
        return cls(RuntimeEventType.OPERATION_RESULT, payload)

    @classmethod
    def delta(cls, content: str) -> RuntimeEvent:
        return cls(RuntimeEventType.DELTA, {"content": content})

    @classmethod
    def final(
        cls,
        content: str,
        sources: Optional[List[dict]] = None,
        run_id: Optional[str] = None,
        **extra: Any,
    ) -> RuntimeEvent:
        payload = {
            "content": content,
            "sources": sources or [],
        }
        if run_id is not None:
            payload["run_id"] = run_id
        payload.update(extra)
        return cls(RuntimeEventType.FINAL, {
            **payload,
        })

    @classmethod
    def error(
        cls,
        message: str,
        recoverable: bool = False,
        *,
        error_code: Optional[RuntimeErrorCode | str] = None,
        retryable: Optional[bool] = None,
    ) -> RuntimeEvent:
        payload: Dict[str, Any] = {
            "error": message,
            "recoverable": recoverable,
        }
        if error_code is not None:
            payload["error_code"] = (
                error_code.value if isinstance(error_code, RuntimeErrorCode) else str(error_code)
            )
        if retryable is not None:
            payload["retryable"] = bool(retryable)
        return cls(RuntimeEventType.ERROR, payload)
