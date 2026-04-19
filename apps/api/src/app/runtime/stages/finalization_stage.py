"""
FinalizationStage — synthesizer + rolling summary + terminal persist.

Invoked by the pipeline when a stage reports NEEDS_FINAL (planner FINAL,
loop-detected, max-iters) OR when triage answered directly (we still want
the rolling summary to roll forward for the next turn).

Responsibilities:
    1. Stream the synthesizer's final answer events (SYNTHESIS phase).
    2. Update memory.status / finished_at.
    3. Invoke SummaryPort to roll the dialogue summary forward.
    4. Persist memory once at the end.

Terminal persistence happens here so the planner/triage stages never have
to care about it after declaring their outcome.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from app.core.logging import get_logger
from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.ports import MemoryPort, SummaryPort, SynthesizerPort

logger = get_logger(__name__)


class FinalizationStage:
    """Produces the final answer stream and commits terminal state."""

    def __init__(
        self,
        *,
        synthesizer: SynthesizerPort,
        summary: SummaryPort,
        memory_port: MemoryPort,
    ) -> None:
        self._synth = synthesizer
        self._summary = summary
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
        """Drive synthesizer → summary → terminal persist.

        If `run_synthesizer` is False (triage direct_answer path), we skip
        the synthesizer step and only handle summary + persist.
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
        await self._roll_summary(memory)
        await self._persist(memory)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    async def _roll_summary(self, memory: WorkingMemory) -> None:
        user_message = memory.question or memory.goal or ""
        assistant_answer = (memory.final_answer or "").strip()
        if not user_message or not assistant_answer:
            return
        try:
            await self._summary.run(
                memory=memory,
                user_message=user_message,
                assistant_answer=assistant_answer,
                recent_messages=[
                    {"role": r.role, "content": r.preview}
                    for r in memory.recent_messages
                ],
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rolling summary update failed: %s", exc)

    async def _persist(self, memory: WorkingMemory) -> None:
        try:
            await self._memory.save(memory)
        except Exception as exc:
            logger.warning(
                "Failed to persist WorkingMemory run=%s: %s", memory.run_id, exc
            )
