"""Runtime stage adapter for the canonical deterministic orchestrator.

The stage translates semantic orchestrator events into the existing phased
event stream.  It is deliberately independent from planner/synthesizer
presentation and can be wired by PipelineAssembler.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from uuid import UUID

from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.orchestrator import DeterministicOrchestrator


class OrchestratorStage:
    def __init__(self, *, orchestrator: DeterministicOrchestrator) -> None:
        self._orchestrator = orchestrator
        self.status = "running"

    async def run(
        self,
        *,
        plan_id: str,
        goal: str,
        available_agents: List[Dict[str, Any]],
        max_steps: int,
        planner_kwargs: Dict[str, Any] | None = None,
    ) -> AsyncIterator[PhasedEvent]:
        async for event in self._orchestrator.run(
            plan_id=plan_id,
            goal=goal,
            available_agents=available_agents,
            max_steps=max_steps,
            **({"planner_kwargs": planner_kwargs} if planner_kwargs is not None else {}),
        ):
            runtime_event = event.to_runtime_event()
            yield PhasedEvent(runtime_event, OrchestrationPhase.PLANNER)
            if event.get("type") == "plan_terminal":
                self.status = str(event.get("status") or "completed")
