from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.sandbox import SandboxRun, SandboxRunStep
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
        return await self.host.runs.get_by_id_with_steps(run_id)

    async def list_runs(
        self,
        *,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[SandboxRun]:
        return await self.host.runs.list_by_session(session_id, branch_id)

    async def list_runs_with_steps_count(
        self,
        *,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[Tuple[SandboxRun, int]]:
        return await self.host.runs.list_by_session_with_steps_count(session_id, branch_id)

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
        paused_action: Dict[str, Any],
        paused_context: Dict[str, Any],
    ) -> Optional[SandboxRun]:
        obj = await self.host.runs.get_by_id(run_id)
        if not obj:
            return None
        return await self.host.runs.update(
            obj,
            {
                "status": "waiting_confirmation",
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

    async def get_run_steps_count(self, run_id: UUID) -> int:
        return await self.host.runs.get_steps_count(run_id)

    async def add_run_step(
        self,
        *,
        run_id: UUID,
        step_type: str,
        step_data: Dict[str, Any],
        order_num: int,
    ) -> SandboxRunStep:
        obj = SandboxRunStep(
            run_id=run_id,
            step_type=step_type,
            step_data=step_data,
            order_num=order_num,
        )
        return await self.host.steps.create(obj)

    async def add_run_steps_bulk(self, run_id: UUID, steps_data: List[Dict[str, Any]]) -> None:
        objs = [
            SandboxRunStep(
                run_id=run_id,
                step_type=s["step_type"],
                step_data=s["step_data"],
                order_num=s["order_num"],
            )
            for s in steps_data
        ]
        await self.host.steps.bulk_create(objs)

    async def list_run_steps(self, run_id: UUID) -> List[SandboxRunStep]:
        return await self.host.steps.list_by_run(run_id)

    async def fail_stale_runs(self, session_id: UUID, stale_threshold_minutes: int = 5) -> int:
        return await self.host.runs.fail_stale_runs(session_id, stale_threshold_minutes)

