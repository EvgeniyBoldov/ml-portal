"""
FinalizationStage — synthesizer stream + terminal state flag.

Invoked by the pipeline when PlanningStage reports NEEDS_FINAL (planner
FINAL, loop-detected, max-iters). The planner's DIRECT_ANSWER path
emits its final event inside PlanningStage itself and does NOT come
through here.

Cross-turn memory is owned by FactStore + DialogueSummaryStore via
MemoryBuilder/MemoryWriter; there is nothing left to persist at the
stage level. The RuntimeTurnState is the single source of truth.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase
from app.runtime.ports import SynthesizerPort
from app.runtime.turn_state import RuntimeTurnState

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
        runtime_state: RuntimeTurnState,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
        run_synthesizer: bool = True,
    ) -> AsyncIterator[PhasedEvent]:
        """Drive synthesizer and set the terminal flags."""
        state = runtime_state
        if run_synthesizer:
            async for event in self._synth.stream(
                runtime_state=state,
                run_id=state.run_id,
                model=model,
                planner_hint=planner_hint,
            ):
                yield PhasedEvent(event, OrchestrationPhase.SYNTHESIS)

        state.status = stop_reason.value
