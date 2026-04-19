"""
FinalizationStage — synthesizer stream + terminal state flag.

Invoked by the pipeline when PlanningStage reports NEEDS_FINAL (planner
FINAL, loop-detected, max-iters). The planner's DIRECT_ANSWER path
emits its final event inside PlanningStage itself and does NOT come
through here.

Post-M6: no persistence anywhere in the pipeline proper. Cross-turn
memory is owned by FactStore + DialogueSummaryStore via
MemoryBuilder/MemoryWriter; there is nothing left to persist at the
stage level. The runtime-state `WorkingMemory` object is scoped to a
single turn and garbage-collected with it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from app.core.logging import get_logger
from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.ports import SynthesizerPort

logger = get_logger(__name__)


class FinalizationStage:
    """Produces the final answer stream and flips the turn to terminal."""

    def __init__(
        self,
        *,
        synthesizer: SynthesizerPort,
    ) -> None:
        self._synth = synthesizer

    async def run(
        self,
        *,
        memory: WorkingMemory,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
        run_synthesizer: bool = True,
    ) -> AsyncIterator[PhasedEvent]:
        """Drive synthesizer and set the in-memory terminal flags."""
        if run_synthesizer:
            async for event in self._synth.stream(
                memory=memory,
                run_id=memory.run_id,
                model=model,
                planner_hint=planner_hint,
            ):
                yield PhasedEvent(event, OrchestrationPhase.SYNTHESIS)

        memory.status = stop_reason.value
        memory.finished_at = datetime.now(timezone.utc)
