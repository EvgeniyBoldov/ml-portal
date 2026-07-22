from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.services.runtime_event_logger import RuntimeEventLogger


@dataclass
class RuntimeEventEmitter:
    """Single pipeline event emission path.

    The emitter owns envelope stamping and sequence progression and is the
    only place where coordinator-level events are turned into wire events.
    """

    stamper: EventEnvelopeStamper
    run_id: str
    logger: RuntimeEventLogger | object | None = None

    def emit(self, event: RuntimeEvent, *, phase: OrchestrationPhase) -> RuntimeEvent:
        return self.stamper.stamp(event, phase, run_id=self.run_id)

    def emit_phased(self, phased: PhasedEvent) -> RuntimeEvent:
        return self.stamper.stamp_phased(phased, run_id=self.run_id)

    async def emit_logged(self, event: RuntimeEvent, *, phase: OrchestrationPhase) -> RuntimeEvent:
        stamped = self.emit(event, phase=phase)
        if self.logger is not None:
            await self.logger.event(
                stamped.type.value,
                payload=dict(stamped.data),
                entity_type=stamped.data.get("entity_type"),
                entity_id=stamped.data.get("entity_id"),
                parent_entity_type=stamped.data.get("parent_entity_type"),
                parent_entity_id=stamped.data.get("parent_entity_id"),
            )
        return stamped

    async def emit_phased_logged(self, phased: PhasedEvent) -> RuntimeEvent:
        return await self.emit_logged(phased.event, phase=phased.phase)

    @property
    def sequence(self) -> int:
        return self.stamper.sequence
