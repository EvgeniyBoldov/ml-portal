from __future__ import annotations

from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent


class PlannerLLMTraceEmitter:
    @staticmethod
    def emit_turn_event(
        *,
        planner_llm_trace,
        planner_iteration_id: str,
        planner_run_id: str,
    ) -> PhasedEvent:
        llm_parent_id = planner_iteration_id
        return PhasedEvent(
            RuntimeEvent.llm_turn(
                llm_call_id=planner_llm_trace.llm_call_id,
                model=planner_llm_trace.model,
                messages=planner_llm_trace.request_messages,
                content=planner_llm_trace.raw_response,
                response_length=planner_llm_trace.response_length,
                tokens_in=planner_llm_trace.tokens_in,
                tokens_out=planner_llm_trace.tokens_out,
                tokens_total=planner_llm_trace.tokens_total,
                duration_ms=planner_llm_trace.duration_ms,
                structured_input=getattr(planner_llm_trace, "structured_input", {}) or {},
                parsed_response=getattr(planner_llm_trace, "parsed_response", {}) or {},
                step_kind=getattr(planner_llm_trace, "step_kind", "decision"),
                parent_entity_type="planner_iteration",
                parent_entity_id=llm_parent_id,
                planner_iteration_id=llm_parent_id,
                planner_run_id=planner_run_id,
                purpose="planning_decision",
                actor_type="planner",
                actor_entity_id=llm_parent_id,
            ),
            OrchestrationPhase.PLANNER,
        )
