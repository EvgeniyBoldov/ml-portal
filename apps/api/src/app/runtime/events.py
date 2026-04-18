"""
Canonical runtime events for the v3 pipeline.

One event model, one envelope, one sequence counter. Consumers:
    * ChatEventMapper (SSE to frontend)
    * Sandbox inspector
    * Trace logger

Envelope fields (phase, sequence, run_id, chat_id) attach on emission
via Pipeline's event emitter — the raw event itself only carries domain data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OrchestrationPhase(str, Enum):
    """Which phase of the pipeline produced the event."""

    TRIAGE = "triage"
    PREFLIGHT = "preflight"
    PLANNER = "planner"
    AGENT = "agent"
    SYNTHESIS = "synthesis"
    PIPELINE = "pipeline"


class RuntimeEventType(str, Enum):
    """Canonical event types. No legacy names — sandbox/SSE mappers adapt to these."""

    # Progress
    STATUS = "status"
    PLANNER_STEP = "planner_step"
    # Operation (tool) execution, emitted by AgentToolRuntime
    OPERATION_CALL = "operation_call"
    OPERATION_RESULT = "operation_result"
    # Streaming answer
    DELTA = "delta"
    FINAL = "final"
    # Interaction
    WAITING_INPUT = "waiting_input"
    CONFIRMATION_REQUIRED = "confirmation_required"
    STOP = "stop"
    # Errors
    ERROR = "error"


@dataclass
class RuntimeEvent:
    """Single event shape streamed out of the runtime."""

    type: RuntimeEventType
    data: Dict[str, Any] = field(default_factory=dict)

    # -------- constructors (keep call-sites terse) --------

    @classmethod
    def status(cls, stage: str, **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.STATUS, {"stage": stage, **extra})

    @classmethod
    def planner_step(cls, *, iteration: int, kind: str, payload: Dict[str, Any]) -> "RuntimeEvent":
        return cls(
            RuntimeEventType.PLANNER_STEP,
            {"iteration": iteration, "kind": kind, **payload},
        )

    @classmethod
    def operation_call(cls, *, operation: str, call_id: str, arguments: Dict[str, Any]) -> "RuntimeEvent":
        return cls(
            RuntimeEventType.OPERATION_CALL,
            {"operation": operation, "call_id": call_id, "arguments": arguments},
        )

    @classmethod
    def operation_result(
        cls, *, operation: str, call_id: str, success: bool, data: Any,
    ) -> "RuntimeEvent":
        return cls(
            RuntimeEventType.OPERATION_RESULT,
            {"operation": operation, "call_id": call_id, "success": success, "data": data},
        )

    @classmethod
    def delta(cls, content: str) -> "RuntimeEvent":
        return cls(RuntimeEventType.DELTA, {"content": content})

    @classmethod
    def final(
        cls,
        content: str,
        sources: Optional[List[dict]] = None,
        run_id: Optional[str] = None,
        **extra: Any,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {"content": content, "sources": sources or []}
        if run_id is not None:
            payload["run_id"] = run_id
        payload.update(extra)
        return cls(RuntimeEventType.FINAL, payload)

    @classmethod
    def waiting_input(cls, question: str, *, run_id: Optional[str] = None) -> "RuntimeEvent":
        data: Dict[str, Any] = {"question": question}
        if run_id:
            data["run_id"] = run_id
        return cls(RuntimeEventType.WAITING_INPUT, data)

    @classmethod
    def confirmation_required(cls, message: str, *, run_id: Optional[str] = None) -> "RuntimeEvent":
        data: Dict[str, Any] = {"message": message}
        if run_id:
            data["run_id"] = run_id
        return cls(RuntimeEventType.CONFIRMATION_REQUIRED, data)

    @classmethod
    def stop(
        cls,
        reason: str,
        *,
        run_id: Optional[str] = None,
        question: Optional[str] = None,
        message: Optional[str] = None,
    ) -> "RuntimeEvent":
        data: Dict[str, Any] = {"reason": reason}
        if run_id is not None:
            data["run_id"] = run_id
        if question:
            data["question"] = question
        if message:
            data["message"] = message
        return cls(RuntimeEventType.STOP, data)

    @classmethod
    def error(cls, message: str, *, recoverable: bool = False) -> "RuntimeEvent":
        return cls(RuntimeEventType.ERROR, {"error": message, "recoverable": recoverable})

    # -------- envelope --------

    def with_envelope(
        self,
        *,
        phase: OrchestrationPhase,
        sequence: int,
        run_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> "RuntimeEvent":
        """Return a copy of this event with orchestration envelope attached in `data`."""
        enriched = dict(self.data)
        enriched["_envelope"] = {
            "phase": phase.value,
            "sequence": sequence,
            "run_id": run_id,
            "chat_id": chat_id,
        }
        return RuntimeEvent(self.type, enriched)
