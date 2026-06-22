from __future__ import annotations

from typing import Any, Dict

from app.runtime.contracts import NextStep
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.turn_state import RuntimeTurnState


class PlannerStepEmitter:
    @staticmethod
    def persist_and_emit_thinking(
        *,
        runtime_state: RuntimeTurnState,
        planner_iteration: int,
        planner_iteration_id: str,
        planner_run_id: str,
        thinking_payload: Dict[str, Any],
    ) -> PhasedEvent:
        step_record = {
            "iteration": planner_iteration,
            "kind": "thinking",
            "phase_id": None,
            "rationale": thinking_payload.get("selection_rationale"),
            "thinking": thinking_payload,
        }
        runtime_state.add_planner_step(step_record)

        payload: Dict[str, Any] = {
            "planner_run_id": planner_run_id,
            "planner_iteration_id": planner_iteration_id,
            "iteration": planner_iteration,
            "parent_entity_type": "planner_iteration",
            "parent_entity_id": planner_iteration_id,
            **thinking_payload,
        }
        return PhasedEvent(
            RuntimeEvent.planner_step(
                iteration=planner_iteration,
                kind="thinking",
                payload=payload,
            ),
            OrchestrationPhase.PLANNER,
        )

    @staticmethod
    def persist_and_emit(
        *,
        runtime_state: RuntimeTurnState,
        step: NextStep,
        planner_iteration: int,
        planner_iteration_id: str,
        planner_run_id: str,
    ) -> PhasedEvent:
        step_record = {
            "iteration": planner_iteration,
            "kind": step.kind.value,
            "agent_slug": step.agent_slug,
            "phase_id": step.phase_id,
            "rationale": step.rationale,
            "agent_input": step.agent_input or {},
        }
        runtime_state.add_planner_step(step_record)

        payload: Dict[str, Any] = {
            "planner_run_id": planner_run_id,
            "planner_iteration_id": planner_iteration_id,
            "iteration": planner_iteration,
            "parent_entity_type": "planner_iteration",
            "parent_entity_id": planner_iteration_id,
            "agent_slug": step.agent_slug,
            "rationale": step.rationale,
            "phase_id": step.phase_id,
            "risk": step.risk,
        }
        return PhasedEvent(
            RuntimeEvent.planner_step(
                iteration=planner_iteration,
                kind=step.kind.value,
                payload=payload,
            ),
            OrchestrationPhase.PLANNER,
        )
