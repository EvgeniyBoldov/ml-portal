from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.turn_state import RuntimeTurnState


@dataclass
class PostCallArbiterResult:
    should_stop: bool
    stop_reason: Optional[PipelineStopReason] = None


class PlannerPostCallArbiter:
    @staticmethod
    def evaluate(
        *,
        runtime_state: RuntimeTurnState,
        planner_run_id: str,
        planner_iteration_id: str,
        planner_iteration: int,
        orchestrator_id: str,
        loop_threshold: int = 3,
    ) -> tuple[list[PhasedEvent], PostCallArbiterResult]:
        events: list[PhasedEvent] = []

        if runtime_state.detect_loop(threshold=loop_threshold):
            runtime_state.add_runtime_fact(
                "Loop detected by runtime; synthesizing from facts.",
                source="pipeline",
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.status(
                        "loop_detected",
                        planner_run_id=planner_run_id,
                        planner_iteration_id=planner_iteration_id,
                        iteration=planner_iteration,
                    ),
                    OrchestrationPhase.PLANNER,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=orchestrator_id,
                        iteration=planner_iteration,
                        status="loop_detected",
                    ),
                    OrchestrationPhase.PLANNER,
                )
            )
            return events, PostCallArbiterResult(
                should_stop=True,
                stop_reason=PipelineStopReason.LOOP_DETECTED,
            )

        events.append(
            PhasedEvent(
                RuntimeEvent.planner_iteration_end(
                    iteration_id=planner_iteration_id,
                    orchestrator_id=orchestrator_id,
                    iteration=planner_iteration,
                    status="completed",
                ),
                OrchestrationPhase.PLANNER,
            )
        )
        return events, PostCallArbiterResult(should_stop=False)
