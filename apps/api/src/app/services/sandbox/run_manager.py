from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.sandbox import SandboxRun
from app.services.sandbox.types import SandboxRunPreparation


class SandboxRunManager:
    """Run lifecycle and run steps operations."""

    def __init__(self, host) -> None:
        self.host = host

    async def create_run(
        self,
        *,
        session_id: UUID,
        branch_id: UUID,
        snapshot_id: UUID,
        request_text: str,
        effective_config: Dict[str, Any],
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxRun:
        obj = SandboxRun(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_id=snapshot_id,
            request_text=request_text,
            effective_config=effective_config,
            parent_run_id=parent_run_id,
            status="running",
        )
        result = await self.host.runs.create(obj)
        await self.host.sessions.touch(session_id)
        return result

    async def prepare_run(
        self,
        *,
        session_id: UUID,
        branch_id: UUID,
        user_id: UUID,
        request_text: str,
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxRunPreparation:
        snapshot = await self.host.branch_state.create_snapshot(
            session_id=session_id,
            branch_id=branch_id,
            user_id=user_id,
        )
        effective_config = await self.host.branch_state.resolve_effective_config_from_snapshot(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_id=snapshot.id,
        )
        run = await self.create_run(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_id=snapshot.id,
            request_text=request_text,
            effective_config=effective_config,
            parent_run_id=parent_run_id,
        )
        return SandboxRunPreparation(
            snapshot=snapshot,
            effective_config=effective_config,
            run=run,
        )

    async def get_run(self, run_id: UUID) -> Optional[SandboxRun]:
        return await self.host.runs.get_by_id(run_id)

    async def get_run_detail(self, run_id: UUID) -> Optional[SandboxRun]:
        return await self.host.runs.get_by_id(run_id)

    async def list_runs(
        self,
        *,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[SandboxRun]:
        return await self.host.runs.list_by_session(session_id, branch_id)

    async def finish_run(
        self,
        *,
        run_id: UUID,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> Optional[SandboxRun]:
        obj = await self.host.runs.get_by_id(run_id)
        if not obj:
            return None
        data: dict = {
            "status": status,
            "finished_at": datetime.now(timezone.utc),
        }
        if error:
            data["error"] = error
        return await self.host.runs.update(obj, data)

    async def pause_run(
        self,
        *,
        run_id: UUID,
        status: str = "waiting_confirmation",
        paused_action: Dict[str, Any],
        paused_context: Dict[str, Any],
    ) -> Optional[SandboxRun]:
        obj = await self.host.runs.get_by_id(run_id)
        if not obj:
            return None
        return await self.host.runs.update(
            obj,
            {
                "status": status,
                "paused_action": paused_action,
                "paused_context": paused_context,
            },
        )

    async def resume_run(self, run_id: UUID) -> Optional[SandboxRun]:
        obj = await self.host.runs.get_by_id(run_id)
        if not obj:
            return None
        return await self.host.runs.update(
            obj,
            {
                "status": "running",
                "paused_action": None,
                "paused_context": None,
            },
        )

    async def update_run_context(
        self,
        run_id: UUID,
        context_snapshot: Dict[str, Any],
    ) -> Optional[SandboxRun]:
        """Update the context_snapshot for a run (used during resume)."""
        obj = await self.host.runs.get_by_id(run_id)
        if not obj:
            return None
        return await self.host.runs.update(
            obj,
            {
                "context_snapshot": context_snapshot,
            },
        )

    async def fail_stale_runs(self, session_id: UUID, stale_threshold_minutes: int = 5) -> int:
        return await self.host.runs.fail_stale_runs(session_id, stale_threshold_minutes)
