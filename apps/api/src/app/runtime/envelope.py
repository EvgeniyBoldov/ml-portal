"""
Event envelope stamping — extracted from RuntimePipeline.

Stages emit bare `(RuntimeEvent, OrchestrationPhase)` tuples via `PhasedEvent`.
The pipeline stamps a monotonic sequence + run_id + chat_id onto every event
before handing it to the transport (SSE / sandbox persistence).

Keeping this in one place means event-ordering semantics live in a single
file and are trivial to test in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.runtime.events import OrchestrationPhase, RuntimeEvent


@dataclass(frozen=True)
class PhasedEvent:
    """A RuntimeEvent annotated with the OrchestrationPhase it belongs to.
    Stages yield these; the pipeline converts them to stamped events."""

    event: RuntimeEvent
    phase: OrchestrationPhase


class EventEnvelopeStamper:
    """Stamps envelope fields (sequence, phase, run_id, chat_id) onto events.

    One instance per pipeline `execute()` call. Sequence is turn-scoped and
    starts at 1.
    """

    __slots__ = ("chat_id", "_seq")

    def __init__(self, chat_id: Optional[str] = None) -> None:
        self.chat_id = chat_id
        self._seq = 0

    def stamp(
        self,
        event: RuntimeEvent,
        phase: OrchestrationPhase,
        run_id: Optional[str] = None,
    ) -> RuntimeEvent:
        self._seq += 1
        return event.with_envelope(
            phase=phase,
            sequence=self._seq,
            run_id=run_id,
            chat_id=self.chat_id,
        )

    def stamp_phased(
        self,
        phased: PhasedEvent,
        run_id: Optional[str] = None,
    ) -> RuntimeEvent:
        return self.stamp(phased.event, phased.phase, run_id=run_id)

    @property
    def sequence(self) -> int:
        return self._seq
