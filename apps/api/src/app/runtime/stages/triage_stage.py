"""
TriageStage — first stage of a runtime turn.

Runs the Triage service and reacts to its decision. Terminal branches
(direct final answer / clarify) are fully handled here; RESUME swaps the
memory in-place; ORCHESTRATE yields to the planning stage.

Events are emitted as PhasedEvent (bare, no envelope) — the pipeline stamps
them. The stage exposes its `outcome` after draining.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from app.runtime.contracts import (
    PipelineRequest,
    PipelineStopReason,
    TriageDecision,
    TriageIntent,
)
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.ports import MemoryPort, TriageServicePort
from app.runtime.resume import ResumeResolver


class TriageOutcomeKind(str, Enum):
    FINAL_ANSWERED = "final_answered"      # pipeline can return
    CLARIFY_PAUSED = "clarify_paused"      # pipeline can return
    PROCEED = "proceed"                    # continue to planning
    RESUMED = "resumed"                    # continue to planning with swapped memory


@dataclass
class TriageOutcome:
    kind: TriageOutcomeKind
    decision: TriageDecision
    memory: WorkingMemory                  # possibly swapped for RESUMED
    stop_reason: Optional[PipelineStopReason] = None


class TriageStage:
    """Executes Triage and emits PhasedEvents. Inspect `.outcome` after run."""

    def __init__(
        self,
        *,
        triage: TriageServicePort,
        memory_port: MemoryPort,
        resume: ResumeResolver,
    ) -> None:
        self._triage = triage
        self._memory = memory_port
        self._resume = resume
        self.outcome: Optional[TriageOutcome] = None

    async def run(
        self,
        *,
        memory: WorkingMemory,
        latest_memory: Optional[WorkingMemory],
        paused_runs: List[WorkingMemory],
        request: PipelineRequest,
        routable_agents: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        chat_id: Optional[UUID],
        user_id: UUID,
        tenant_id: UUID,
    ) -> AsyncIterator[PhasedEvent]:
        yield PhasedEvent(
            RuntimeEvent.status("pipeline_started", run_id=str(memory.run_id)),
            OrchestrationPhase.PIPELINE,
        )
        await self._memory.save(memory)

        yield PhasedEvent(
            RuntimeEvent.status("triage"),
            OrchestrationPhase.TRIAGE,
        )

        decision = await self._triage.decide(
            request_text=request.request_text,
            memory=latest_memory or memory,
            routable_agents=routable_agents,
            paused_runs=paused_runs,
            platform_config=platform_config,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        memory.intent = decision.intent.value
        memory.goal = decision.goal or memory.goal or request.request_text
        await self._memory.save(memory)

        yield PhasedEvent(
            RuntimeEvent.status(
                "triage_complete",
                intent=decision.intent.value,
                confidence=decision.confidence,
                reason=decision.reason,
            ),
            OrchestrationPhase.TRIAGE,
        )

        # --- FINAL: direct answer from triage.
        if decision.intent == TriageIntent.FINAL:
            async for ev in self._emit_direct_answer(memory, decision):
                yield ev
            self.outcome = TriageOutcome(
                kind=TriageOutcomeKind.FINAL_ANSWERED,
                decision=decision,
                memory=memory,
                stop_reason=PipelineStopReason.COMPLETED,
            )
            return

        # --- CLARIFY: ask for more info and pause.
        if decision.intent == TriageIntent.CLARIFY:
            async for ev in self._emit_clarify(memory, decision):
                yield ev
            self.outcome = TriageOutcome(
                kind=TriageOutcomeKind.CLARIFY_PAUSED,
                decision=decision,
                memory=memory,
                stop_reason=PipelineStopReason.WAITING_INPUT,
            )
            return

        # --- RESUME: swap memory with the paused one if it exists.
        if decision.intent == TriageIntent.RESUME and decision.resume_run_id is not None:
            resumed = await self._resume.resume(decision.resume_run_id)
            if resumed is not None:
                memory = resumed
                await self._memory.save(memory)
                yield PhasedEvent(
                    RuntimeEvent.status("resumed_paused_run", run_id=str(memory.run_id)),
                    OrchestrationPhase.TRIAGE,
                )
                self.outcome = TriageOutcome(
                    kind=TriageOutcomeKind.RESUMED,
                    decision=decision,
                    memory=memory,
                )
                return
            # Resume failed — fall through to orchestrate with fresh memory.

        self.outcome = TriageOutcome(
            kind=TriageOutcomeKind.PROCEED,
            decision=decision,
            memory=memory,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _emit_direct_answer(
        self,
        memory: WorkingMemory,
        decision: TriageDecision,
    ) -> AsyncIterator[PhasedEvent]:
        answer = decision.answer or ""
        yield PhasedEvent(RuntimeEvent.status("direct_answer"), OrchestrationPhase.TRIAGE)
        for i in range(0, len(answer), 20):
            yield PhasedEvent(
                RuntimeEvent.delta(answer[i : i + 20]),
                OrchestrationPhase.TRIAGE,
            )
        memory.final_answer = answer
        memory.status = PipelineStopReason.COMPLETED.value
        memory.finished_at = datetime.now(timezone.utc)

    async def _emit_clarify(
        self,
        memory: WorkingMemory,
        decision: TriageDecision,
    ) -> AsyncIterator[PhasedEvent]:
        question = (
            decision.clarify_prompt
            or "Уточни, пожалуйста, что именно ты хочешь сделать?"
        )
        memory.add_open_question(question)
        memory.status = PipelineStopReason.WAITING_INPUT.value
        yield PhasedEvent(
            RuntimeEvent.waiting_input(question, run_id=str(memory.run_id)),
            OrchestrationPhase.TRIAGE,
        )
        yield PhasedEvent(
            RuntimeEvent.stop(
                PipelineStopReason.WAITING_INPUT.value,
                run_id=str(memory.run_id),
                question=question,
            ),
            OrchestrationPhase.TRIAGE,
        )
