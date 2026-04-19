"""
FinalizationStage — synthesizer + terminal persist.

Invoked by the pipeline when PlanningStage reports NEEDS_FINAL (planner
FINAL, loop-detected, max-iters). The planner's DIRECT_ANSWER path
emits its final event inside PlanningStage itself and does NOT come
through here.

Cross-turn summary rolling was a concern of this stage in the v3.0
pipeline; it now lives in `MemoryWriter` (which the pipeline invokes
after every turn — success, pause, or abort). This stage only owns
the synthesizer stream and writing the terminal state of the legacy
WorkingMemory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from app.core.logging import get_logger
from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.ports import MemoryPort, SynthesizerPort

logger = get_logger(__name__)


class FinalizationStage:
    """Produces the final answer stream and commits terminal state."""

    def __init__(
        self,
        *,
        synthesizer: SynthesizerPort,
        memory_port: MemoryPort,
    ) -> None:
        self._synth = synthesizer
        self._memory = memory_port

    async def run(
        self,
        *,
        memory: WorkingMemory,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
        run_synthesizer: bool = True,
    ) -> AsyncIterator[PhasedEvent]:
        """Drive synthesizer → terminal persist.

        `run_synthesizer=False` is retained as a kwarg for the rare case
        where a caller needs the terminal-persist side effect without a
        synth stream (currently unused). Default behaviour runs the
        synthesizer.
        """
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
        await self._persist(memory)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    async def _persist(self, memory: WorkingMemory) -> None:
        try:
            await self._memory.save(memory)
        except Exception as exc:
            logger.warning(
                "Failed to persist WorkingMemory run=%s: %s", memory.run_id, exc
            )
