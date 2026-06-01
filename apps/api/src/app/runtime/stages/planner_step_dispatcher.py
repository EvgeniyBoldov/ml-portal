from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.runtime.contracts import NextStep, NextStepKind, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.planner.iteration_policy import build_iteration_result
from app.runtime.turn_state import RuntimeTurnState


@dataclass
class TerminalDispatchResult:
    outcome_kind: Literal["direct", "needs_final", "paused", "aborted"]
    stop_reason: PipelineStopReason
    planner_hint: Optional[str] = None
    final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize"
    error_message: Optional[str] = None


class PlannerStepDispatcher:
    """Dispatches non-agent terminal planner steps."""

    @staticmethod
    def dispatch_terminal_step(
        *,
        step: NextStep,
        runtime_state: RuntimeTurnState,
        run_id: str,
        planner_iteration: int,
        planner_iteration_id: str,
        orchestrator_id: str,
    ) -> tuple[list[PhasedEvent], Optional[TerminalDispatchResult]]:
        events: list[PhasedEvent] = []

        if step.kind == NextStepKind.DIRECT_ANSWER:
            answer = (step.final_answer or "").strip()
            if not answer:
                answer = (step.rationale or "").strip() or "Не удалось сформировать ответ."
            synthesis_id = f"{run_id}:planner-direct"
            runtime_state.final_answer = answer
            runtime_state.status = PipelineStopReason.COMPLETED.value
            events.append(
                PhasedEvent(
                    RuntimeEvent.synthesis_start(
                        synthesis_id=synthesis_id,
                        run_id=str(run_id),
                        role="planner_direct",
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
            )
            if answer:
                events.append(
                    PhasedEvent(
                        RuntimeEvent.delta(answer),
                        OrchestrationPhase.SYNTHESIS,
                    )
                )
            events.append(
                PhasedEvent(
                    RuntimeEvent.status(
                        "final_answer_marker",
                        producer="planner_direct",
                        parent_entity_type="synthesis_run",
                        parent_entity_id=synthesis_id,
                        content=answer,
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.final(answer, sources=[], run_id=str(run_id)),
                    OrchestrationPhase.SYNTHESIS,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.synthesis_end(
                        synthesis_id=synthesis_id,
                        run_id=str(run_id),
                        status="completed",
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
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
            runtime_state.add_iteration_result(
                build_iteration_result(
                    state=runtime_state,
                    iteration=planner_iteration,
                    step_kind=step.kind.value,
                    agent_slug=step.agent_slug,
                    phase_id=step.phase_id,
                    outcome="direct_answer",
                    summary=answer,
                    sufficient_for_phase=True,
                )
            )
            return events, TerminalDispatchResult(
                outcome_kind="direct",
                stop_reason=PipelineStopReason.COMPLETED,
                planner_hint=answer,
            )

        if step.kind == NextStepKind.FINAL:
            runtime_state.status = PipelineStopReason.COMPLETED.value
            runtime_state.add_iteration_result(
                build_iteration_result(
                    state=runtime_state,
                    iteration=planner_iteration,
                    step_kind=step.kind.value,
                    agent_slug=step.agent_slug,
                    phase_id=step.phase_id,
                    outcome="final",
                    summary=str(step.final_answer or ""),
                    sufficient_for_phase=True,
                )
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
            return events, TerminalDispatchResult(
                outcome_kind="needs_final",
                stop_reason=PipelineStopReason.COMPLETED,
                planner_hint=step.final_answer,
                final_answer_strategy=step.final_answer_strategy,
            )

        if step.kind in (NextStepKind.ASK_USER, NextStepKind.CLARIFY):
            question = step.question or "Нужны дополнительные данные для продолжения."
            if question not in runtime_state.open_questions:
                runtime_state.open_questions.append(question)
            runtime_state.status = PipelineStopReason.WAITING_INPUT.value
            events.append(
                PhasedEvent(
                    RuntimeEvent.stop(
                        PipelineStopReason.WAITING_INPUT.value,
                        run_id=str(run_id),
                        question=question,
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
                        status="paused",
                    ),
                    OrchestrationPhase.PLANNER,
                )
            )
            runtime_state.add_iteration_result(
                build_iteration_result(
                    state=runtime_state,
                    iteration=planner_iteration,
                    step_kind=step.kind.value,
                    agent_slug=None,
                    phase_id=step.phase_id,
                    outcome="needs_input",
                    summary=question,
                    question=question,
                    sufficient_for_phase=False,
                )
            )
            return events, TerminalDispatchResult(
                outcome_kind="paused",
                stop_reason=PipelineStopReason.WAITING_INPUT,
            )

        if step.kind == NextStepKind.ABORT:
            runtime_state.status = PipelineStopReason.ABORTED.value
            runtime_state.final_error = step.rationale
            final_text = (step.final_answer or "").strip() if hasattr(step, "final_answer") else ""
            if not final_text:
                reason = (step.rationale or "").strip()
                final_text = f"Выполнение остановлено. {reason}" if reason else "Выполнение остановлено."
            runtime_state.final_answer = final_text
            runtime_state.add_iteration_result(
                build_iteration_result(
                    state=runtime_state,
                    iteration=planner_iteration,
                    step_kind=step.kind.value,
                    agent_slug=None,
                    phase_id=step.phase_id,
                    outcome="aborted",
                    summary=str(step.rationale or ""),
                    sufficient_for_phase=False,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.error(
                        f"Aborted: {step.rationale}",
                        recoverable=False,
                        parent_entity_type="planner_iteration",
                        parent_entity_id=planner_iteration_id,
                    ),
                    OrchestrationPhase.PLANNER,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.status(
                        "final_answer_marker",
                        producer="planner_abort",
                        parent_entity_type="planner_iteration",
                        parent_entity_id=planner_iteration_id,
                        content=final_text,
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.final(
                        final_text,
                        sources=[],
                        run_id=str(run_id),
                        stop_reason=PipelineStopReason.ABORTED.value,
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
            )
            events.append(
                PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=orchestrator_id,
                        iteration=planner_iteration,
                        status="aborted",
                    ),
                    OrchestrationPhase.PLANNER,
                )
            )
            return events, TerminalDispatchResult(
                outcome_kind="aborted",
                stop_reason=PipelineStopReason.ABORTED,
                error_message=step.rationale,
            )

        return events, None
