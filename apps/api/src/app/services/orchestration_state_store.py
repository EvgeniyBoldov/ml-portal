from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from app.services.execution_memory_service import ExecutionMemoryService
from app.services.orchestration_state import OrchestrationState


class OrchestrationStateStore:
    """Adapter that persists orchestration state using ExecutionMemoryService."""

    STATE_KEY = "orchestration_state_v2"

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def load(self, run_id: UUID) -> Optional[OrchestrationState]:
        if not self.session_factory:
            return None
        async with self.session_factory() as session:
            service = ExecutionMemoryService(session)
            snapshot = await service.snapshot(run_id)
            raw_state = (snapshot.get("memory_state") or {}).get(self.STATE_KEY)
            if not isinstance(raw_state, dict):
                return None
            return OrchestrationState.model_validate(raw_state)

    async def update(
        self,
        run_id: UUID,
        *,
        chat_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        goal: Optional[str] = None,
        current_phase_id: Optional[str] = None,
        current_agent_slug: Optional[str] = None,
        patch: Optional[Dict[str, Any]] = None,
    ) -> Optional[OrchestrationState]:
        if not self.session_factory:
            return None
        existing = await self.load(run_id)
        merged = existing.model_dump() if existing else OrchestrationState(run_id=str(run_id)).model_dump()
        if patch:
            merged.update(patch)
        if chat_id is not None:
            merged["chat_id"] = chat_id
        if tenant_id is not None:
            merged["tenant_id"] = tenant_id
        if goal is not None:
            merged["goal"] = goal
        if current_phase_id is not None:
            merged["current_phase_id"] = current_phase_id
        if current_agent_slug is not None:
            merged["current_agent_slug"] = current_agent_slug
        state = OrchestrationState.model_validate(merged)

        async with self.session_factory() as session:
            service = ExecutionMemoryService(session)
            await service.update_context(
                run_id=run_id,
                chat_id=UUID(chat_id) if chat_id else None,
                tenant_id=UUID(tenant_id) if tenant_id else None,
                goal=goal,
                current_phase_id=current_phase_id,
                current_agent_slug=current_agent_slug,
                state={self.STATE_KEY: state.model_dump()},
            )
            await session.commit()
        return state

    async def snapshot(self, run_id: UUID) -> Dict[str, Any]:
        state = await self.load(run_id)
        return state.model_dump() if state else {}
