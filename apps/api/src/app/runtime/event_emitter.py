from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent


@dataclass
class RuntimeEventEmitter:
    """Single pipeline event emission path.

    The emitter owns envelope stamping and sequence progression and is the
    only place where coordinator-level events are turned into wire events.
    """

    stamper: EventEnvelopeStamper
    run_id: str

    def emit(self, event: RuntimeEvent, *, phase: OrchestrationPhase) -> RuntimeEvent:
        return self.stamper.stamp(event, phase, run_id=self.run_id)

    def emit_phased(self, phased: PhasedEvent) -> RuntimeEvent:
        return self.stamper.stamp_phased(phased, run_id=self.run_id)

    @property
    def sequence(self) -> int:
        return self.stamper.sequence
