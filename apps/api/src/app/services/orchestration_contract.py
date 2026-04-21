from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.agents.contracts import ActionType, RuntimeTriageDecision
from app.runtime.events import RuntimeEvent


class IntentType(str, Enum):
    FINAL = "final"
    CLARIFY = "clarify"
    ORCHESTRATE = "orchestrate"


class IntentDecision(BaseModel):
    type: IntentType
    confidence: float = 0.0
    answer: Optional[str] = None
    clarify_prompt: Optional[str] = None
    goal: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None


class PlannerStepType(str, Enum):
    CALL_AGENT = "call_agent"
    ASK_USER = "ask_user"
    FINALIZE = "finalize"
    OPERATION_CALL = "operation_call"
    UNKNOWN = "unknown"


class PlannerStepDecision(BaseModel):
    step_type: PlannerStepType
    action_type: str
    agent_slug: Optional[str] = None
    question: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    why: Optional[str] = None

    def to_runtime_payload(self, iteration: int) -> Dict[str, Any]:
        return {
            "iteration": iteration,
            "action_type": self.action_type,
            "agent_slug": self.agent_slug,
            "phase_id": self.phase_id,
            "phase_title": self.phase_title,
            "why": self.why,
            "step_type": self.step_type.value,
        }

    def signature(self, fallback_phase_id: Optional[str] = None) -> str:
        phase = self.phase_id or fallback_phase_id or "none"
        return f"{self.action_type}:{self.agent_slug or 'none'}:{phase}"


class OrchestrationPhase(str, Enum):
    PIPELINE = "pipeline"
    TRIAGE = "triage"
    PLANNER = "planner"


class OrchestrationEventEnvelope(BaseModel):
    phase: OrchestrationPhase
    event_type: str
    stage: Optional[str] = None
    run_id: Optional[str] = None
    chat_id: Optional[str] = None
    sequence: int = 0
    ts: str


def attach_orchestration_envelope(
    event: RuntimeEvent,
    *,
    phase: OrchestrationPhase,
    sequence: int,
    run_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> RuntimeEvent:
    data = dict(event.data or {})
    envelope = OrchestrationEventEnvelope(
        phase=phase,
        event_type=event.type.value,
        stage=str(data.get("stage") or "") or None,
        run_id=run_id,
        chat_id=chat_id,
        sequence=sequence,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    data["orchestration_envelope"] = envelope.model_dump()
    return RuntimeEvent(event.type, data)


def intent_from_runtime_triage(decision: RuntimeTriageDecision) -> IntentDecision:
    return IntentDecision(
        type=IntentType(decision.type),
        confidence=decision.confidence,
        answer=decision.answer,
        clarify_prompt=decision.clarify_prompt,
        goal=decision.goal,
        inputs=decision.inputs or {},
        trace_id=decision.trace_id,
    )


def runtime_triage_from_intent(intent: IntentDecision) -> RuntimeTriageDecision:
    return RuntimeTriageDecision(
        type=intent.type.value,
        confidence=intent.confidence,
        answer=intent.answer,
        clarify_prompt=intent.clarify_prompt,
        goal=intent.goal,
        inputs=intent.inputs or {},
        trace_id=intent.trace_id,
    )


def planner_step_from_next_action(next_action: Any) -> PlannerStepDecision:
    action_type = str(getattr(getattr(next_action, "type", None), "value", "unknown"))
    meta = getattr(next_action, "meta", None)
    phase_id = getattr(meta, "phase_id", None) if meta else None
    phase_title = getattr(meta, "phase_title", None) if meta else None
    why = getattr(meta, "why", None) if meta else None

    if getattr(next_action, "type", None) == ActionType.AGENT_CALL:
        agent = getattr(next_action, "agent", None)
        return PlannerStepDecision(
            step_type=PlannerStepType.CALL_AGENT,
            action_type=action_type,
            agent_slug=getattr(agent, "agent_slug", None),
            phase_id=phase_id,
            phase_title=phase_title,
            why=why,
        )

    if getattr(next_action, "type", None) == ActionType.ASK_USER:
        ask_user = getattr(next_action, "ask_user", None)
        return PlannerStepDecision(
            step_type=PlannerStepType.ASK_USER,
            action_type=action_type,
            question=getattr(ask_user, "question", None),
            phase_id=phase_id,
            phase_title=phase_title,
            why=why,
        )

    if getattr(next_action, "type", None) == ActionType.FINAL:
        return PlannerStepDecision(
            step_type=PlannerStepType.FINALIZE,
            action_type=action_type,
            phase_id=phase_id,
            phase_title=phase_title,
            why=why,
        )

    if getattr(next_action, "type", None) == ActionType.OPERATION_CALL:
        return PlannerStepDecision(
            step_type=PlannerStepType.OPERATION_CALL,
            action_type=action_type,
            phase_id=phase_id,
            phase_title=phase_title,
            why=why,
        )

    return PlannerStepDecision(
        step_type=PlannerStepType.UNKNOWN,
        action_type=action_type,
        phase_id=phase_id,
        phase_title=phase_title,
        why=why,
    )
