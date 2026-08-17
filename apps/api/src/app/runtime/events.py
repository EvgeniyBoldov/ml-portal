"""
Canonical runtime events for the v3 pipeline.

One event model, one journal-assigned envelope. Consumers:
    * ChatEventMapper (SSE to frontend)
    * Sandbox inspector
    * Trace logger

Envelope fields attach only after the journal has persisted the row and
assigned its DB sequence — the raw event itself only carries domain data.
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
    ORCHESTRATOR_CHECKPOINT_STARTED = "orchestrator_checkpoint_started"
    ORCHESTRATOR_CHECKPOINT_FINISHED = "orchestrator_checkpoint_finished"
    # Lifecycle — planner iteration
    PLANNER_ITERATION_START = "planner_iteration_start"
    PLANNER_ITERATION_END = "planner_iteration_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    PLANNER_INVOCATION_STARTED = "planner_invocation_started"
    PLANNER_INVOCATION_FINISHED = "planner_invocation_finished"
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
    BUDGET_CONSUMED = "budget_consumed"
    BUDGET_REJECTED = "budget_rejected"
    PREFLIGHT_SNAPSHOT = "preflight_snapshot"
    PREFLIGHT_STARTED = "preflight_started"
    PREFLIGHT_COMPLETED = "preflight_completed"
    PREFLIGHT_FAILED = "preflight_failed"
    RBAC_SNAPSHOT = "rbac_snapshot"
    LIMITS_SNAPSHOT = "limits_snapshot"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    # Tool execution
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_COMPLETED = "extraction_completed"
    EXTRACTION_FAILED = "extraction_failed"
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
    # Canonical persisted plan/task lifecycle
    PLAN_CREATED = "plan_created"
    PLAN_PATCH_APPLIED = "plan_patch_applied"
    PLAN_WAITING_INPUT = "plan_waiting_input"
    PLAN_COMPLETED = "plan_completed"
    PLAN_FAILED = "plan_failed"
    TASK_READY = "task_ready"
    TASK_CLAIMED = "task_claimed"
    TASK_STARTED = "task_started"
    TASK_PAUSED = "task_paused"
    TASK_RESUMED = "task_resumed"
    TASK_COMPLETED = "task_completed"
    TASK_UNFULFILLABLE = "task_unfulfillable"
    TASK_FAILED = "task_failed"
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_SUCCEEDED = "attempt_succeeded"
    ATTEMPT_FAILED = "attempt_failed"
    ATTEMPT_RETRY_SCHEDULED = "attempt_retry_scheduled"
    REQUIREMENT_CREATED = "requirement_created"
    REQUIREMENT_RESOLVED = "requirement_resolved"
    REQUIREMENT_UNRESOLVABLE = "requirement_unresolvable"


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
        cls, *, iteration_id: str, orchestrator_id: str, iteration: int,
        iteration_type: str = "decision", **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.PLANNER_ITERATION_START, {
            "entity_id": iteration_id, "entity_type": "planner_iteration",
            "parent_entity_type": "orchestrator", "parent_entity_id": orchestrator_id,
            "iteration": iteration, "iteration_type": iteration_type, **extra,
        })

    @classmethod
    def planner_iteration_end(
        cls, *, iteration_id: str, orchestrator_id: str, iteration: int,
        status: str = "completed", iteration_type: str = "decision", **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.PLANNER_ITERATION_END, {
            "entity_id": iteration_id, "entity_type": "planner_iteration",
            "parent_entity_type": "orchestrator", "parent_entity_id": orchestrator_id,
            "iteration": iteration, "iteration_type": iteration_type, "status": status, **extra,
        })

    @classmethod
    def step_start(
        cls, *, step_id: str, iteration_id: str, kind: str, title: Optional[str] = None,
        objective: Optional[str] = None, intent: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None, risk: Optional[str] = None,
        **extra: Any,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {
            "entity_id": step_id, "entity_type": "step",
            "parent_entity_type": "planner_iteration", "parent_entity_id": iteration_id,
            "kind": kind,
        }
        for key, value in {
            "title": title, "objective": objective, "intent": intent,
            "inputs": inputs, "risk": risk,
        }.items():
            if value not in (None, "", {}, []):
                payload[key] = value
        payload.update(extra)
        return cls(RuntimeEventType.STEP_START, payload)

    @classmethod
    def step_end(
        cls, *, step_id: str, iteration_id: str, status: str,
        outcome: Optional[str] = None, summary: Optional[str] = None,
        sufficient_for_phase: Optional[bool] = None, **extra: Any,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {
            "entity_id": step_id, "entity_type": "step",
            "parent_entity_type": "planner_iteration", "parent_entity_id": iteration_id,
            "status": status,
        }
        for key, value in {
            "outcome": outcome, "summary": summary,
            "sufficient_for_phase": sufficient_for_phase,
        }.items():
            if value is not None and value != "":
                payload[key] = value
        payload.update(extra)
        return cls(RuntimeEventType.STEP_END, payload)

    @classmethod
    def agent_start(
        cls, *, agent_execution_id: str,
        parent_entity_id: str, parent_entity_type: str = "planner_iteration",
        agent_slug: str, executor_type: str = "agent", executor_name: Optional[str] = None,
        task_title: Optional[str] = None, **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.AGENT_START, {
            "entity_id": agent_execution_id, "entity_type": "agent_execution",
            "parent_entity_type": parent_entity_type, "parent_entity_id": parent_entity_id,
            "agent_slug": agent_slug,
            "executor_type": executor_type,
            "executor_name": executor_name or ("Планер" if agent_slug == "planner" else agent_slug),
            **({"task_title": task_title} if task_title else {}),
            **extra,
        })

    @classmethod
    def agent_end(
        cls, *, agent_execution_id: str,
        parent_entity_id: str, parent_entity_type: str = "planner_iteration",
        agent_slug: str, status: str = "completed", **extra: Any
    ) -> "RuntimeEvent":
        return cls(RuntimeEventType.AGENT_END, {
            "entity_id": agent_execution_id, "entity_type": "agent_execution",
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
    def plan_lifecycle(cls, event_type: RuntimeEventType, *, plan_id: str, **extra: Any) -> "RuntimeEvent":
        if event_type not in {
            RuntimeEventType.PLAN_CREATED,
            RuntimeEventType.PLAN_PATCH_APPLIED,
            RuntimeEventType.PLAN_WAITING_INPUT,
            RuntimeEventType.PLAN_COMPLETED,
            RuntimeEventType.PLAN_FAILED,
        }:
            raise ValueError(f"not a plan event: {event_type}")
        return cls(event_type, {"entity_id": plan_id, "entity_type": "plan", **extra})

    @classmethod
    def task_lifecycle(cls, event_type: RuntimeEventType, *, plan_id: str, task_id: str, **extra: Any) -> "RuntimeEvent":
        allowed = {
            RuntimeEventType.TASK_READY,
            RuntimeEventType.TASK_CLAIMED,
            RuntimeEventType.TASK_STARTED,
            RuntimeEventType.TASK_PAUSED,
            RuntimeEventType.TASK_RESUMED,
            RuntimeEventType.TASK_COMPLETED,
            RuntimeEventType.TASK_UNFULFILLABLE,
            RuntimeEventType.TASK_FAILED,
        }
        if event_type not in allowed:
            raise ValueError(f"not a task event: {event_type}")
        return cls(event_type, {
            "entity_id": task_id,
            "entity_type": "task",
            "parent_entity_type": "plan",
            "parent_entity_id": plan_id,
            **extra,
        })

    @classmethod
    def attempt_lifecycle(cls, event_type: RuntimeEventType, *, task_id: str, attempt_id: str, **extra: Any) -> "RuntimeEvent":
        allowed = {
            RuntimeEventType.ATTEMPT_STARTED,
            RuntimeEventType.ATTEMPT_SUCCEEDED,
            RuntimeEventType.ATTEMPT_FAILED,
            RuntimeEventType.ATTEMPT_RETRY_SCHEDULED,
        }
        if event_type not in allowed:
            raise ValueError(f"not an attempt event: {event_type}")
        return cls(event_type, {
            "entity_id": attempt_id,
            "entity_type": "attempt",
            "parent_entity_type": "task",
            "parent_entity_id": task_id,
            **extra,
        })

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
    def llm_request(cls, **payload: Any) -> "RuntimeEvent":
        data = dict(payload)
        data.setdefault("entity_type", "llm_call")
        data.setdefault("entity_id", data.get("llm_call_id"))
        data.setdefault("status", "running")
        return cls(RuntimeEventType.LLM_REQUEST, data)

    @classmethod
    def llm_response(cls, **payload: Any) -> "RuntimeEvent":
        data = dict(payload)
        data.setdefault("entity_type", "llm_call")
        data.setdefault("entity_id", data.get("llm_call_id"))
        # A provider marked as non-retryable can never be in the retry wait
        # state. Keep the invariant at the canonical event boundary so stale
        # callers cannot publish a contradictory trace.
        if data.get("retryable") is False and data.get("status") == "waiting_retry":
            data["status"] = "failed"
            data["terminal"] = True
        if "status" not in data:
            data["status"] = "failed" if data.get("error_type") or data.get("error_code") else "completed"
        return cls(RuntimeEventType.LLM_RESPONSE, data)

    @classmethod
    def tool_call(
        cls,
        *,
        tool: str,
        call_id: str,
        arguments: Dict[str, Any],
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
        agent_execution_id: Optional[str] = None,
        llm_call_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_entity_id: Optional[str] = None,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {
            "entity_type": "tool_call", "entity_id": call_id,
            "tool": tool, "call_id": call_id, "arguments": arguments,
            "status": "running",
        }
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        if agent_slug is not None:
            payload["agent_slug"] = agent_slug
        if agent_execution_id is not None:
            payload["agent_execution_id"] = agent_execution_id
        if llm_call_id is not None:
            payload["llm_call_id"] = llm_call_id
        if actor_type is not None:
            payload["actor_type"] = actor_type
        if actor_entity_id is not None:
            payload["actor_entity_id"] = actor_entity_id
        return cls(RuntimeEventType.TOOL_CALL, payload)

    @classmethod
    def tool_result(
        cls,
        *,
        tool: str,
        call_id: str,
        success: bool,
        data: Any,
        sources: Optional[list[dict[str, Any]]] = None,
        error_code: Optional[RuntimeErrorCode | str] = None,
        retryable: Optional[bool] = None,
        safe_message: Optional[str] = None,
        user_message: Optional[str] = None,
        operator_message: Optional[str] = None,
        source: Optional[str] = None,
        debug: Optional[Dict[str, Any]] = None,
        envelope: Optional[Dict[str, Any]] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
        agent_execution_id: Optional[str] = None,
        llm_call_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_entity_id: Optional[str] = None,
        reused: Optional[bool] = None,
        reused_from_call_id: Optional[str] = None,
        truncated: Optional[bool] = None,
    ) -> "RuntimeEvent":
        payload: Dict[str, Any] = {
            "entity_type": "tool_call",
            "entity_id": call_id,
            "tool": tool,
            "call_id": call_id,
            "success": success,
            "status": "completed" if success else "failed",
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
        if user_message is not None:
            payload["user_message"] = user_message
        if operator_message is not None:
            payload["operator_message"] = operator_message
        if source is not None:
            payload["source"] = source
        if debug is not None:
            payload["debug"] = dict(debug)
        if envelope is not None:
            payload["result"] = dict(envelope)
        if parent_entity_type is not None:
            payload["parent_entity_type"] = parent_entity_type
        if parent_entity_id is not None:
            payload["parent_entity_id"] = parent_entity_id
        if agent_slug is not None:
            payload["agent_slug"] = agent_slug
        if agent_execution_id is not None:
            payload["agent_execution_id"] = agent_execution_id
        if llm_call_id is not None:
            payload["llm_call_id"] = llm_call_id
        if actor_type is not None:
            payload["actor_type"] = actor_type
        if actor_entity_id is not None:
            payload["actor_entity_id"] = actor_entity_id
        if reused is not None:
            payload["reused"] = bool(reused)
        if reused_from_call_id is not None:
            payload["reused_from_call_id"] = reused_from_call_id
        if truncated is not None:
            payload["truncated"] = bool(truncated)
        return cls(RuntimeEventType.TOOL_RESULT, payload)

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
    def waiting_input(
        cls,
        question: str,
        *,
        run_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
        interaction_kind: str = "clarify",
    ) -> "RuntimeEvent":
        data: Dict[str, Any] = {"question": question}
        if run_id:
            data["run_id"] = run_id
        if entity_id:
            data.update({
                "entity_type": "interaction",
                "entity_id": entity_id,
                "interaction_kind": interaction_kind,
            })
        if parent_entity_type:
            data["parent_entity_type"] = parent_entity_type
        if parent_entity_id:
            data["parent_entity_id"] = parent_entity_id
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
        entity_id: Optional[str] = None,
        parent_entity_type: Optional[str] = None,
        parent_entity_id: Optional[str] = None,
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
        if entity_id:
            data.update({
                "entity_type": "interaction",
                "entity_id": entity_id,
                "interaction_kind": "confirm",
            })
        if parent_entity_type:
            data["parent_entity_type"] = parent_entity_type
        if parent_entity_id:
            data["parent_entity_id"] = parent_entity_id
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
        action: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "RuntimeEvent":
        data: Dict[str, Any] = {"reason": reason}
        if run_id is not None:
            data["run_id"] = run_id
        if question:
            data["question"] = question
        if message:
            data["message"] = message
        if action:
            data["action"] = dict(action)
        if context:
            data["context"] = dict(context)
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
        payload: Dict[str, Any] = {"error": message, "recoverable": recoverable, "level": "error"}
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
        event_id: Optional[str] = None,
        occurred_at: Optional[str] = None,
    ) -> "RuntimeEvent":
        """Return a copy of this event with orchestration envelope attached in `data`."""
        enriched = dict(self.data)
        enriched["_envelope"] = {
            "phase": phase.value,
            "sequence": sequence,
            "run_id": run_id,
            "chat_id": chat_id,
            "event_id": event_id,
            "occurred_at": occurred_at,
        }
        return RuntimeEvent(self.type, enriched)
