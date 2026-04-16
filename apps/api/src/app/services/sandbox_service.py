"""
Sandbox service — session lifecycle, overrides, run management.

Commit is done in routers, not here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.sandbox import (
    SandboxBranch,
    SandboxBranchOverride,
    SandboxOverrideSnapshot,
    SandboxOverride,
    SandboxRun,
    SandboxRunStep,
    SandboxSession,
)
from app.repositories.sandbox_repository import (
    SandboxBranchOverrideRepository,
    SandboxBranchRepository,
    SandboxOverrideRepository,
    SandboxSnapshotRepository,
    SandboxRunRepository,
    SandboxRunStepRepository,
    SandboxSessionRepository,
)
from app.services.sandbox.types import SandboxRunPreparation
from app.services.sandbox.branch_state_manager import SandboxBranchStateManager
from app.services.sandbox.override_manager import SandboxOverrideManager
from app.services.sandbox.run_manager import SandboxRunManager

logger = get_logger(__name__)


class SandboxService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.sessions = SandboxSessionRepository(session)
        self.branches = SandboxBranchRepository(session)
        self.branch_overrides = SandboxBranchOverrideRepository(session)
        self.snapshots = SandboxSnapshotRepository(session)
        self.overrides = SandboxOverrideRepository(session)
        self.runs = SandboxRunRepository(session)
        self.steps = SandboxRunStepRepository(session)
        self.branch_state = SandboxBranchStateManager(self)
        self.override_manager = SandboxOverrideManager(self)
        self.run_manager = SandboxRunManager(self)

    DEFAULT_BRANCH_NAME = "main"

    # ── Session lifecycle ────────────────────────────────────────────────

    async def create_session(
        self,
        owner_id: UUID,
        tenant_id: UUID,
        name: Optional[str] = None,
        ttl_days: int = 14,
    ) -> SandboxSession:
        now = datetime.now(timezone.utc)
        obj = SandboxSession(
            owner_id=owner_id,
            tenant_id=tenant_id,
            name=name or f"Sandbox {now.strftime('%d.%m %H:%M')}",
            ttl_days=ttl_days,
            last_activity_at=now,
            expires_at=now + timedelta(days=ttl_days),
        )
        session_obj = await self.sessions.create(obj)
        await self.ensure_default_branch(session_obj.id, owner_id)
        return session_obj

    async def ensure_default_branch(self, session_id: UUID, user_id: UUID) -> SandboxBranch:
        existing = await self.branches.list_by_session(session_id)
        if existing:
            return existing[0]
        branch = SandboxBranch(
            session_id=session_id,
            name=self.DEFAULT_BRANCH_NAME,
            created_by=user_id,
            parent_branch_id=None,
            parent_run_id=None,
        )
        return await self.branches.create(branch)

    async def get_session(self, session_id: UUID) -> Optional[SandboxSession]:
        return await self.sessions.get_by_id(session_id)

    async def get_session_detail(self, session_id: UUID) -> Optional[SandboxSession]:
        return await self.sessions.get_by_id_with_relations(session_id)

    async def list_sessions(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[SandboxSession], int]:
        return await self.sessions.list_sessions(tenant_id, status, skip, limit)

    async def list_sessions_with_counts(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Tuple[SandboxSession, int, int]], int]:
        return await self.sessions.list_sessions_with_counts(tenant_id, status, skip, limit)

    async def update_session(
        self, session_id: UUID, data: dict
    ) -> Optional[SandboxSession]:
        obj = await self.sessions.get_by_id(session_id)
        if not obj:
            return None
        if "ttl_days" in data and data["ttl_days"] is not None:
            now = datetime.now(timezone.utc)
            data["expires_at"] = now + timedelta(days=data["ttl_days"])
        return await self.sessions.update(obj, data)

    async def delete_session(self, session_id: UUID) -> bool:
        obj = await self.sessions.get_by_id(session_id)
        if not obj:
            return False
        await self.sessions.delete(obj)
        return True

    async def touch_session(self, session_id: UUID) -> None:
        await self.sessions.touch(session_id)

    async def is_owner(self, session_id: UUID, user_id: UUID) -> bool:
        obj = await self.sessions.get_by_id(session_id)
        if not obj:
            return False
        return obj.owner_id == user_id

    async def get_overrides_count(self, session_id: UUID) -> int:
        return await self.sessions.get_overrides_count(session_id)

    async def get_runs_count(self, session_id: UUID) -> int:
        return await self.sessions.get_runs_count(session_id)

    # ── Branches / Branch overrides / Snapshots ─────────────────────────

    async def list_branches(self, session_id: UUID) -> List[SandboxBranch]:
        return await self.branch_state.list_branches(session_id)

    async def get_branch(self, branch_id: UUID) -> Optional[SandboxBranch]:
        return await self.branch_state.get_branch(branch_id)

    async def create_branch(
        self,
        session_id: UUID,
        user_id: UUID,
        name: str,
        parent_branch_id: Optional[UUID] = None,
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxBranch:
        return await self.branch_state.create_branch(
            session_id=session_id,
            user_id=user_id,
            name=name,
            parent_branch_id=parent_branch_id,
            parent_run_id=parent_run_id,
        )

    async def fork_branch(
        self,
        session_id: UUID,
        source_branch_id: UUID,
        user_id: UUID,
        name: str,
        parent_run_id: Optional[UUID] = None,
        copy_overrides: bool = True,
    ) -> SandboxBranch:
        return await self.branch_state.fork_branch(
            session_id=session_id,
            source_branch_id=source_branch_id,
            user_id=user_id,
            name=name,
            parent_run_id=parent_run_id,
            copy_overrides=copy_overrides,
        )

    async def list_branch_overrides(self, branch_id: UUID) -> List[SandboxBranchOverride]:
        return await self.branch_state.list_branch_overrides(branch_id)

    async def upsert_branch_override(
        self,
        branch_id: UUID,
        user_id: UUID,
        entity_type: str,
        field_path: str,
        value_json: Dict[str, Any] | List[Any] | str | int | float | bool | None,
        value_type: str = "json",
        entity_id: Optional[UUID] = None,
    ) -> SandboxBranchOverride:
        return await self.branch_state.upsert_branch_override(
            branch_id=branch_id,
            user_id=user_id,
            entity_type=entity_type,
            field_path=field_path,
            value_json=value_json,
            value_type=value_type,
            entity_id=entity_id,
        )

    async def delete_branch_override(
        self,
        branch_id: UUID,
        entity_type: str,
        field_path: str,
        entity_id: Optional[UUID] = None,
    ) -> bool:
        return await self.branch_state.delete_branch_override(
            branch_id=branch_id,
            entity_type=entity_type,
            field_path=field_path,
            entity_id=entity_id,
        )

    async def delete_branch_overrides_for_entity(
        self,
        branch_id: UUID,
        entity_type: str,
        entity_id: Optional[UUID] = None,
    ) -> int:
        return await self.branch_state.delete_branch_overrides_for_entity(
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    async def reset_branch_overrides(self, branch_id: UUID) -> int:
        return await self.branch_state.reset_branch_overrides(branch_id)

    async def create_snapshot(
        self,
        session_id: UUID,
        branch_id: UUID,
        user_id: UUID,
    ) -> SandboxOverrideSnapshot:
        return await self.branch_state.create_snapshot(
            session_id=session_id,
            branch_id=branch_id,
            user_id=user_id,
        )

    async def get_snapshot(self, snapshot_id: UUID) -> Optional[SandboxOverrideSnapshot]:
        return await self.branch_state.get_snapshot(snapshot_id)

    # ── Overrides ────────────────────────────────────────────────────────

    async def create_override(
        self,
        session_id: UUID,
        entity_type: str,
        label: str,
        config_snapshot: Dict[str, Any],
        entity_id: Optional[UUID] = None,
        is_active: bool = False,
    ) -> SandboxOverride:
        return await self.override_manager.create_override(
            session_id=session_id,
            entity_type=entity_type,
            label=label,
            config_snapshot=config_snapshot,
            entity_id=entity_id,
            is_active=is_active,
        )

    async def update_override(
        self, override_id: UUID, data: dict
    ) -> Optional[SandboxOverride]:
        return await self.override_manager.update_override(override_id, data)

    async def activate_override(self, override_id: UUID) -> Optional[SandboxOverride]:
        return await self.override_manager.activate_override(override_id)

    async def delete_override(self, override_id: UUID) -> bool:
        return await self.override_manager.delete_override(override_id)

    async def reset_overrides(self, session_id: UUID) -> int:
        return await self.override_manager.reset_overrides(session_id)

    async def list_overrides(self, session_id: UUID) -> List[SandboxOverride]:
        return await self.override_manager.list_overrides(session_id)

    async def get_active_overrides(self, session_id: UUID) -> List[SandboxOverride]:
        return await self.override_manager.get_active_overrides(session_id)

    # ── Runs ─────────────────────────────────────────────────────────────

    async def create_run(
        self,
        session_id: UUID,
        branch_id: UUID,
        snapshot_id: UUID,
        request_text: str,
        effective_config: Dict[str, Any],
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxRun:
        return await self.run_manager.create_run(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_id=snapshot_id,
            request_text=request_text,
            effective_config=effective_config,
            parent_run_id=parent_run_id,
        )

    async def prepare_run(
        self,
        *,
        session_id: UUID,
        branch_id: UUID,
        user_id: UUID,
        request_text: str,
        parent_run_id: Optional[UUID] = None,
    ) -> SandboxRunPreparation:
        """Create snapshot, resolve effective config, and create run in one contract."""
        return await self.run_manager.prepare_run(
            session_id=session_id,
            branch_id=branch_id,
            user_id=user_id,
            request_text=request_text,
            parent_run_id=parent_run_id,
        )

    async def get_run(self, run_id: UUID) -> Optional[SandboxRun]:
        return await self.run_manager.get_run(run_id)

    async def get_run_detail(self, run_id: UUID) -> Optional[SandboxRun]:
        return await self.run_manager.get_run_detail(run_id)

    async def list_runs(
        self,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[SandboxRun]:
        return await self.run_manager.list_runs(session_id=session_id, branch_id=branch_id)

    async def list_runs_with_steps_count(
        self,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[Tuple[SandboxRun, int]]:
        return await self.run_manager.list_runs_with_steps_count(
            session_id=session_id, branch_id=branch_id
        )

    async def finish_run(
        self,
        run_id: UUID,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> Optional[SandboxRun]:
        return await self.run_manager.finish_run(
            run_id=run_id,
            status=status,
            error=error,
        )

    async def pause_run(
        self,
        run_id: UUID,
        paused_action: Dict[str, Any],
        paused_context: Dict[str, Any],
    ) -> Optional[SandboxRun]:
        return await self.run_manager.pause_run(
            run_id=run_id,
            paused_action=paused_action,
            paused_context=paused_context,
        )

    async def resume_run(self, run_id: UUID) -> Optional[SandboxRun]:
        return await self.run_manager.resume_run(run_id)

    async def get_run_steps_count(self, run_id: UUID) -> int:
        return await self.run_manager.get_run_steps_count(run_id)

    # ── Run Steps ────────────────────────────────────────────────────────

    async def add_run_step(
        self,
        run_id: UUID,
        step_type: str,
        step_data: Dict[str, Any],
        order_num: int,
    ) -> SandboxRunStep:
        return await self.run_manager.add_run_step(
            run_id=run_id,
            step_type=step_type,
            step_data=step_data,
            order_num=order_num,
        )

    async def add_run_steps_bulk(
        self, run_id: UUID, steps_data: List[Dict[str, Any]]
    ) -> None:
        await self.run_manager.add_run_steps_bulk(run_id, steps_data)

    async def list_run_steps(self, run_id: UUID) -> List[SandboxRunStep]:
        return await self.run_manager.list_run_steps(run_id)

    # ── Effective Config ─────────────────────────────────────────────────

    async def resolve_effective_config_from_snapshot(
        self,
        session_id: UUID,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> Dict[str, Any]:
        """Build effective config from immutable snapshot payload."""
        return await self.branch_state.resolve_effective_config_from_snapshot(
            session_id=session_id,
            branch_id=branch_id,
            snapshot_id=snapshot_id,
        )

    async def fail_stale_runs(
        self, session_id: UUID, stale_threshold_minutes: int = 5
    ) -> int:
        """Mark zombie runs (running > threshold) as failed."""
        return await self.run_manager.fail_stale_runs(session_id, stale_threshold_minutes)

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def cleanup_expired(self) -> int:
        return await self.sessions.archive_expired()
