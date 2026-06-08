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

from app.runtime.operation_errors import RuntimeErrorCode

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

    # Lifecycle — run
    RUN_START = "run_start"
    RUN_END = "run_end"
    # Lifecycle — orchestrator (planner loop)
    ORCHESTRATOR_START = "orchestrator_start"
    ORCHESTRATOR_END = "orchestrator_end"
    # Lifecycle — planner iteration
    PLANNER_ITERATION_START = "planner_iteration_start"
    PLANNER_ITERATION_END = "planner_iteration_end"
    # Lifecycle — agent
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    # Lifecycle — synthesis
    SYNTHESIS_START = "synthesis_start"
    SYNTHESIS_END = "synthesis_end"
    # Progress
    STATUS = "status"
    PLANNER_DECISION = "planner_decision"
    PROTOCOL_RETRY = "protocol_retry"
    INTENT = "intent"
    BUDGET_SNAPSHOT = "budget_snapshot"
    LLM_TURN = "llm_turn"
    # Operation (tool) execution, emitted by AgentToolRuntime
    OPERATION_CALL = "operation_call"
    OPERATION_RESULT = "operation_result"
    # Streaming answer
    DELTA = "delta"
    FINAL = "final"
    # Interaction
    WAITING_INPUT = "waiting_input"
    CONFIRMATION_REQUIRED = "confirmation_required"
    QUESTION_ANSWER = "question_answer"
    STOP = "stop"
    # Errors
    ERROR = "error"


@dataclass
class RuntimeEvent:
    """Single event shape streamed out of the runtime."""

    type: RuntimeEventType
    data: Dict[str, Any] = field(default_factory=dict)

    # -------- lifecycle constructors --------

    @classmethod
    def run_start(cls, *, run_id: str, **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.RUN_START, {"entity_id": run_id, "entity_type": "run", **extra})

    @classmethod
    def run_end(cls, *, run_id: str, status: str = "completed", **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.RUN_END, {"entity_id": run_id, "entity_type": "run", "status": status, **extra})

    @classmethod
    def orchestrator_start(cls, *, orchestrator_id: str, run_id: str, role: str = "planner", **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.ORCHESTRATOR_START, {
            "entity_id": orchestrator_id, "entity_type": "orchestrator",
            "parent_entity_type": "run", "parent_entity_id": run_id,
            "role": role, **extra,
        })

    @classmethod
    def orchestrator_end(cls, *, orchestrator_id: str, run_id: str, status: str = "completed", **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.ORCHESTRATOR_END, {
            "entity_id": orchestrator_id, "entity_type": "orchestrator",
            "parent_entity_type": "run", "parent_entity_id": run_id,
            "status": status, **extra,
        })

    @classmethod
    def planner_iteration_start(
        cls, *, iteration_id: str, orchestrator_id: str, iteration: int, **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.PLANNER_ITERATION_START, {
            "entity_id": iteration_id, "entity_type": "planner_iteration",
            "parent_entity_type": "orchestrator", "parent_entity_id": orchestrator_id,
            "iteration": iteration, **extra,
        })

    @classmethod
    def planner_iteration_end(
        cls, *, iteration_id: str, orchestrator_id: str, iteration: int, status: str = "completed", **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.PLANNER_ITERATION_END, {
            "entity_id": iteration_id, "entity_type": "planner_iteration",
            "parent_entity_type": "orchestrator", "parent_entity_id": orchestrator_id,
            "iteration": iteration, "status": status, **extra,
        })

    @classmethod
    def agent_start(
        cls, *, agent_run_id: str, parent_entity_id: str, parent_entity_type: str = "planner_iteration",
        agent_slug: str, **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.AGENT_START, {
            "entity_id": agent_run_id, "entity_type": "agent_run",
            "parent_entity_type": parent_entity_type, "parent_entity_id": parent_entity_id,
            "agent_slug": agent_slug, **extra,
        })

    @classmethod
    def agent_end(
        cls, *, agent_run_id: str, parent_entity_id: str, parent_entity_type: str = "planner_iteration",
        agent_slug: str, status: str = "completed", **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.AGENT_END, {
            "entity_id": agent_run_id, "entity_type": "agent_run",
            "parent_entity_type": parent_entity_type, "parent_entity_id": parent_entity_id,
            "agent_slug": agent_slug, "status": status, **extra,
        })

    @classmethod
    def synthesis_start(cls, *, synthesis_id: str, run_id: str, **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.SYNTHESIS_START, {
            "entity_id": synthesis_id, "entity_type": "synthesis_run",
            "parent_entity_type": "run", "parent_entity_id": run_id, **extra,
        })

    @classmethod
    def synthesis_end(cls, *, synthesis_id: str, run_id: str, status: str = "completed", **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.SYNTHESIS_END, {
            "entity_id": synthesis_id, "entity_type": "synthesis_run",
            "parent_entity_type": "run", "parent_entity_id": run_id,
            "status": status, **extra,
        })

    # -------- constructors (keep call-sites terse) --------

    @classmethod
    def status(cls, stage: str, **extra: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.STATUS, {"stage": stage, **extra})

    @classmethod
    def planner_step(cls, *, iteration: int, kind: str, payload: Dict[str, Any]) -> "RuntimeEvent":
        return cls(
            RuntimeEventType.PLANNER_DECISION,
            {"iteration": iteration, "kind": kind, **payload},
        )

    @classmethod
    def planner_decision(cls, *, iteration: int, kind: str, payload: Dict[str, Any]) -> "RuntimeEvent":
        return cls(
            RuntimeEventType.PLANNER_DECISION,
            {"iteration": iteration, "kind": kind, **payload},
        )

    @classmethod
    def budget_snapshot(
        cls,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        own: Optional[Dict[str, Any]] = None,
        limits: Optional[Dict[str, Any]] = None,
        delta: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        at_ms: Optional[int] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        role: Optional[str] = None,
        # legacy compatibility
        owner_scope: Optional[str] = None,
        owner_id: Optional[str] = None,
        snapshot: Optional[Dict[str, Any]] = None,
        parent_owner_id: Optional[str] = None,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {}

        if entity_type is not None or entity_id is not None or own is not None or limits is not None:
            payload.update({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "own": own or {},
                "limits": limits,
            })
            if role is not None:
                payload["role"] = role
        else:
            payload.update({
                "owner_scope": owner_scope,
                "owner_id": owner_id,
                "snapshot": snapshot or {},
            })

        if delta is not None:
            payload["delta"] = delta
        if reason is not None:
            payload["reason"] = reason
        if at_ms is not None:
            payload["at_ms"] = at_ms
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        if parent_owner_id is not None:
            payload["parent_owner_id"] = parent_owner_id
        return cls(RuntimeEventType.BUDGET_SNAPSHOT, payload)

    @classmethod
    def llm_turn(cls, **payload: Any) -> "RuntimeEvent":
        return cls(RuntimeEventType.LLM_TURN, dict(payload))

    @classmethod
    def operation_call(
        cls,
        *,
        operation: str,
        call_id: str,
        arguments: Dict[str, Any],
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        llm_call_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_entity_id: Optional[str] = None,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {"operation": operation, "call_id": call_id, "arguments": arguments}
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        if agent_slug is not None:
            payload["agent_slug"] = agent_slug
        if agent_run_id is not None:
            payload["agent_run_id"] = agent_run_id
        if llm_call_id is not None:
            payload["llm_call_id"] = llm_call_id
        if actor_type is not None:
            payload["actor_type"] = actor_type
        if actor_entity_id is not None:
            payload["actor_entity_id"] = actor_entity_id
        return cls(RuntimeEventType.OPERATION_CALL, payload)

    @classmethod
    def operation_result(
        cls,
        *,
        operation: str,
        call_id: str,
        success: bool,
        data: Any,
        sources: Optional[list[dict[str, Any]]] = None,
        error_code: Optional[RuntimeErrorCode | str] = None,
        retryable: Optional[bool] = None,
        safe_message: Optional[str] = None,
        envelope: Optional[Dict[str, Any]] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        llm_call_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_entity_id: Optional[str] = None,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {
            "operation": operation,
            "call_id": call_id,
            "success": success,
            "data": data,
        }
        if sources is not None:
            payload["sources"] = list(sources)
        if error_code is not None:
            payload["error_code"] = (
                error_code.value if isinstance(error_code, RuntimeErrorCode) else str(error_code)
            )
        if retryable is not None:
            payload["retryable"] = bool(retryable)
        if safe_message is not None:
            payload["safe_message"] = safe_message
        if envelope is not None:
            payload["result"] = dict(envelope)
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        if agent_slug is not None:
            payload["agent_slug"] = agent_slug
        if agent_run_id is not None:
            payload["agent_run_id"] = agent_run_id
        if llm_call_id is not None:
            payload["llm_call_id"] = llm_call_id
        if actor_type is not None:
            payload["actor_type"] = actor_type
        if actor_entity_id is not None:
            payload["actor_entity_id"] = actor_entity_id
        return cls(RuntimeEventType.OPERATION_RESULT, payload)

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
    def confirmation_required(
        cls,
        message: str,
        *,
        run_id: Optional[str] = None,
        operation_fingerprint: Optional[str] = None,
        tool_slug: Optional[str] = None,
        operation: Optional[str] = None,
        risk_level: Optional[str] = None,
        args_preview: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> "RuntimeEvent":
        data: Dict[str, Any] = {"message": message}
        if run_id:
            data["run_id"] = run_id
        if operation_fingerprint:
            data["operation_fingerprint"] = operation_fingerprint
        if tool_slug:
            data["tool_slug"] = tool_slug
        if operation:
            data["operation"] = operation
        if risk_level:
            data["risk_level"] = risk_level
        if args_preview:
            data["args_preview"] = args_preview
        if summary:
            data["summary"] = summary
        return cls(RuntimeEventType.CONFIRMATION_REQUIRED, data)

    @classmethod
    def question_answer(
        cls,
        *,
        interaction_id: str,
        parent_entity_id: str,
        resume_action: str,
        question: Optional[str] = None,
        user_answer: Optional[str] = None,
        source_run_id: Optional[str] = None,
        question_kind: Optional[str] = None,
    ) -> "RuntimeEvent":
        data: Dict[str, Any] = {
            "entity_id": interaction_id,
            "entity_type": "question_answer",
            "parent_entity_type": "orchestrator",
            "parent_entity_id": parent_entity_id,
            "resume_action": resume_action,
        }
        if question:
            data["question"] = question
        if user_answer:
            data["user_answer"] = user_answer
        if source_run_id:
            data["source_run_id"] = source_run_id
        if question_kind:
            data["question_kind"] = question_kind
        return cls(RuntimeEventType.QUESTION_ANSWER, data)

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
    def error(
        cls,
        message: str,
        *,
        recoverable: bool = False,
        error_code: Optional[RuntimeErrorCode | str] = None,
        retryable: Optional[bool] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        **extra: Any,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {"error": message, "recoverable": recoverable}
        if error_code is not None:
            payload["error_code"] = (
                error_code.value if isinstance(error_code, RuntimeErrorCode) else str(error_code)
            )
        if retryable is not None:
            payload["retryable"] = bool(retryable)
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        payload.update(extra)
        return cls(RuntimeEventType.ERROR, payload)

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
