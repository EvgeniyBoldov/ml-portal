"""
PlanningStage — the planner loop.

For each iteration:
    1. Ask Planner for the next NextStep.
    2. Record it into WorkingMemory + emit a PLANNER_STEP event.
    3. Dispatch on kind:
         CALL_AGENT → AgentExecutionPort.execute(...) → stream events
         ASK_USER   → terminal (waiting_input)
         FINAL      → terminal (completed) — finalization runs next
         ABORT      → terminal (aborted)
    4. Loop detection → terminal (loop_detected).
    5. Max-iters   → terminal (max_iters).

The stage does not finalize by itself; it reports a PlanningOutcome and
FinalizationStage handles synthesizer + rolling summary + terminal persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from app.agents.context import ToolContext
from app.core.logging import get_logger
from app.runtime.contracts import (
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
)
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.memory.working_memory import (
    PlannerStepRecord,
    WorkingMemory,
)
from app.runtime.ports import (
    AgentExecutionPort,
    MemoryPort,
    PlannerServicePort,
)

logger = get_logger(__name__)


class PlanningOutcomeKind(str, Enum):
    NEEDS_FINAL = "needs_final"        # synthesizer should run
    PAUSED = "paused"                  # ASK_USER — stop, no synth
    ABORTED = "aborted"                # planner-driven abort
    FAILED = "failed"                  # planner raised


@dataclass
class PlanningOutcome:
    kind: PlanningOutcomeKind
    stop_reason: PipelineStopReason
    planner_hint: Optional[str] = None      # final_answer hint from planner
    error_message: Optional[str] = None


class PlanningStage:
    """Runs the planner loop. Dispatches to AgentExecutionPort for CALL_AGENT."""

    def __init__(
        self,
        *,
        planner: PlannerServicePort,
        agent_executor: AgentExecutionPort,
        memory_port: MemoryPort,
        max_iterations: int,
        max_wall_time_ms: int,
    ) -> None:
        self._planner = planner
        self._agent = agent_executor
        self._memory = memory_port
        self._max_iterations = max_iterations
        self._max_wall_time_ms = max_wall_time_ms  # reserved for deadline checks
        self.outcome: Optional[PlanningOutcome] = None

    async def run(
        self,
        *,
        memory: WorkingMemory,
        request: PipelineRequest,
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        available_agents: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
    ) -> AsyncIterator[PhasedEvent]:
        run_id = memory.run_id
        chat_id = memory.chat_id
        memory.goal = memory.goal or request.request_text

        while memory.iter_count < self._max_iterations:
            yield PhasedEvent(
                RuntimeEvent.status(
                    "planner_thinking", iteration=memory.iter_count + 1
                ),
                OrchestrationPhase.PLANNER,
            )

            try:
                step = await self._planner.next_step(
                    memory=memory,
                    available_agents=available_agents,
                    outline=memory.outline,
                    platform_config=platform_config,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=run_id,
                )
            except Exception as exc:
                logger.error(
                    "Planner failure on iter=%s: %s", memory.iter_count, exc, exc_info=True
                )
                memory.status = PipelineStopReason.FAILED.value
                memory.final_error = f"planner_exception: {exc}"
                memory.finished_at = datetime.now(timezone.utc)
                await self._memory.save(memory)
                yield PhasedEvent(
                    RuntimeEvent.error(f"Planner failed: {exc}", recoverable=False),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.FAILED,
                    stop_reason=PipelineStopReason.FAILED,
                    error_message=str(exc),
                )
                return

            step_record = PlannerStepRecord(
                iteration=memory.iter_count + 1,
                kind=step.kind.value,
                agent_slug=step.agent_slug,
                phase_id=step.phase_id,
                rationale=step.rationale,
            )
            memory.add_planner_step(step_record)
            await self._memory.save(memory)

            yield PhasedEvent(
                RuntimeEvent.planner_step(
                    iteration=step_record.iteration,
                    kind=step.kind.value,
                    payload={
                        "agent_slug": step.agent_slug,
                        "rationale": step.rationale,
                        "phase_id": step.phase_id,
                        "risk": step.risk,
                    },
                ),
                OrchestrationPhase.PLANNER,
            )

            # Loop detection is driven by sub-agent action signatures, not
            # planner records — check after agent execution below.

            # --- Dispatch -------------------------------------------------
            if step.kind == NextStepKind.FINAL:
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.COMPLETED,
                    planner_hint=step.final_answer,
                )
                return

            if step.kind == NextStepKind.ASK_USER:
                question = step.question or "Нужны дополнительные данные для продолжения."
                memory.add_open_question(question)
                memory.status = PipelineStopReason.WAITING_INPUT.value
                await self._memory.save(memory)
                yield PhasedEvent(
                    RuntimeEvent.waiting_input(question, run_id=str(run_id)),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.stop(
                        PipelineStopReason.WAITING_INPUT.value,
                        run_id=str(run_id),
                        question=question,
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.PAUSED,
                    stop_reason=PipelineStopReason.WAITING_INPUT,
                )
                return

            if step.kind == NextStepKind.ABORT:
                memory.status = PipelineStopReason.ABORTED.value
                memory.final_error = step.rationale
                memory.finished_at = datetime.now(timezone.utc)
                await self._memory.save(memory)
                yield PhasedEvent(
                    RuntimeEvent.error(f"Aborted: {step.rationale}", recoverable=False),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.ABORTED,
                    stop_reason=PipelineStopReason.ABORTED,
                    error_message=step.rationale,
                )
                return

            # kind == CALL_AGENT
            async for event in self._agent.execute(
                step=step,
                memory=memory,
                messages=request.messages,
                ctx=ctx,
                user_id=user_id,
                tenant_id=tenant_id,
                platform_config=platform_config,
                sandbox_overrides=request.sandbox_overrides,
                model=request.model,
            ):
                yield PhasedEvent(event, OrchestrationPhase.AGENT)

            await self._memory.save(memory)

            if memory.detect_loop():
                memory.add_fact(
                    "Loop detected by runtime; synthesizing from facts.",
                    source="pipeline",
                )
                yield PhasedEvent(
                    RuntimeEvent.status("loop_detected"),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.LOOP_DETECTED,
                    planner_hint=None,
                )
                return

        # Max iterations reached → synthesize whatever we have.
        yield PhasedEvent(
            RuntimeEvent.status("max_iters_reached", iterations=memory.iter_count),
            OrchestrationPhase.PLANNER,
        )
        self.outcome = PlanningOutcome(
            kind=PlanningOutcomeKind.NEEDS_FINAL,
            stop_reason=PipelineStopReason.MAX_ITERS,
            planner_hint=None,
        )
