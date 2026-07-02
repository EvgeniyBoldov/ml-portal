from __future__ import annotations

from dataclasses import dataclass
import traceback
from typing import Optional

from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.error_payloads import build_debug_payload
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.llm.limits import LLMLimitExceededError


@dataclass
class PlannerFailureResult:
    final_error: str
    error_message: str
    error_event: PhasedEvent
    iteration_end_event: PhasedEvent


class PlannerFailureHandler:
    @staticmethod
    def from_exception(
        *,
        exc: Exception,
        planner_iteration_id: str,
        orchestrator_id: str,
        planner_iteration: int,
    ) -> PlannerFailureResult:
        error_code: Optional[str] = None
        if isinstance(exc, LLMLimitExceededError):
            error_code = exc.code
        return PlannerFailureResult(
            final_error=f"planner_exception: {exc}",
            error_message=str(exc),
            error_event=PhasedEvent(
                RuntimeEvent.error(
                    f"Planner failed: {exc}",
                    recoverable=False,
                    error_code=error_code,
                    user_message=f"Planner failed: {exc}",
                    operator_message=str(exc),
                    source="runtime",
                    debug=build_debug_payload(exc=exc, traceback_text=traceback.format_exc()),
                    parent_entity_type="planner_iteration",
                    parent_entity_id=planner_iteration_id,
                ),
                OrchestrationPhase.PLANNER,
            ),
            iteration_end_event=PhasedEvent(
                RuntimeEvent.planner_iteration_end(
                    iteration_id=planner_iteration_id,
                    orchestrator_id=orchestrator_id,
                    iteration=planner_iteration,
                    status=PipelineStopReason.FAILED.value,
                ),
                OrchestrationPhase.PLANNER,
            ),
        )
