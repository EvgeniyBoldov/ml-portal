"""Phase annotation for events before the journal assigns their envelope."""
from __future__ import annotations

from dataclasses import dataclass
from app.runtime.events import OrchestrationPhase, RuntimeEvent


@dataclass(frozen=True)
class PhasedEvent:
    """A RuntimeEvent annotated with the OrchestrationPhase it belongs to.
    Stages yield these; the pipeline converts them to stamped events."""

    event: RuntimeEvent
    phase: OrchestrationPhase
