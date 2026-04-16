"""
Runtime events — типы событий, которые runtime стримит наружу.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    ) -> RuntimeEvent:
        return cls(RuntimeEventType.OPERATION_RESULT, {
            "operation": operation_slug,
            "call_id": call_id,
            "success": success,
            "data": data,
        })

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
    def error(cls, message: str, recoverable: bool = False) -> RuntimeEvent:
        return cls(RuntimeEventType.ERROR, {
            "error": message,
            "recoverable": recoverable,
        })
