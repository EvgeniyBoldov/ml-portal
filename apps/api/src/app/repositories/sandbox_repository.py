"""
Sandbox repositories — sessions, overrides, runs, run steps.

All repos use flush() only. Commit is done in routers/services.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sandbox import (
    SandboxBranch,
    SandboxBranchOverride,
    SandboxSession,
    SandboxOverride,
    SandboxOverrideSnapshot,
    SandboxRun,
    SandboxRunStep,
)


class SandboxSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxSession) -> SandboxSession:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, session_id: UUID) -> Optional[SandboxSession]:
        stmt = select(SandboxSession).where(SandboxSession.id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(self, session_id: UUID) -> Optional[SandboxSession]:
        stmt = (
            select(SandboxSession)
            .where(SandboxSession.id == session_id)
            .options(
                selectinload(SandboxSession.overrides),
                selectinload(SandboxSession.runs),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[SandboxSession], int]:
        base = select(SandboxSession).where(SandboxSession.tenant_id == tenant_id)
        if status:
            base = base.where(SandboxSession.status == status)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = await self.session.scalar(count_stmt) or 0

        stmt = base.order_by(SandboxSession.last_activity_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_sessions_with_counts(
        self,
        tenant_id: UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Tuple[SandboxSession, int, int]], int]:
        """List sessions with overrides_count and runs_count (no N+1)."""
        base_filter = SandboxSession.tenant_id == tenant_id
        status_filter = SandboxSession.status == status if status else None

        overrides_sq = (
            select(
                SandboxOverride.session_id,
                func.count().label("overrides_count"),
            )
            .where(SandboxOverride.is_active == True)
            .group_by(SandboxOverride.session_id)
            .subquery()
        )
        runs_sq = (
            select(
                SandboxRun.session_id,
                func.count().label("runs_count"),
            )
            .group_by(SandboxRun.session_id)
            .subquery()
        )

        stmt = (
            select(
                SandboxSession,
                func.coalesce(overrides_sq.c.overrides_count, 0),
                func.coalesce(runs_sq.c.runs_count, 0),
            )
            .outerjoin(overrides_sq, SandboxSession.id == overrides_sq.c.session_id)
            .outerjoin(runs_sq, SandboxSession.id == runs_sq.c.session_id)
            .where(base_filter)
        )
        if status_filter is not None:
            stmt = stmt.where(status_filter)

        count_base = select(SandboxSession).where(base_filter)
        if status_filter is not None:
            count_base = count_base.where(status_filter)
        total = await self.session.scalar(select(func.count()).select_from(count_base.subquery())) or 0

        stmt = stmt.order_by(SandboxSession.last_activity_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        rows = [(row[0], row[1], row[2]) for row in result.all()]
        return rows, total

    async def update(self, obj: SandboxSession, data: dict) -> SandboxSession:
        for key, value in data.items():
            setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def touch(self, session_id: UUID) -> None:
        """Sliding TTL: update last_activity_at and recalculate expires_at."""
        obj = await self.get_by_id(session_id)
        if not obj:
            return
        now = datetime.now(timezone.utc)
        obj.last_activity_at = now
        obj.expires_at = now + timedelta(days=obj.ttl_days)
        self.session.add(obj)
        await self.session.flush()

    async def delete(self, obj: SandboxSession) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def archive_expired(self) -> int:
        """Archive sessions past their expires_at."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(SandboxSession)
            .where(
                and_(
                    SandboxSession.status == "active",
                    SandboxSession.expires_at < now,
                )
            )
            .values(status="archived")
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_overrides_count(self, session_id: UUID) -> int:
        stmt = select(func.count()).where(SandboxOverride.session_id == session_id)
        return await self.session.scalar(stmt) or 0

    async def get_runs_count(self, session_id: UUID) -> int:
        stmt = select(func.count()).where(SandboxRun.session_id == session_id)
        return await self.session.scalar(stmt) or 0


class SandboxOverrideRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxOverride) -> SandboxOverride:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, override_id: UUID) -> Optional[SandboxOverride]:
        stmt = select(SandboxOverride).where(SandboxOverride.id == override_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_session(self, session_id: UUID) -> List[SandboxOverride]:
        stmt = (
            select(SandboxOverride)
            .where(SandboxOverride.session_id == session_id)
            .order_by(SandboxOverride.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, obj: SandboxOverride, data: dict) -> SandboxOverride:
        for key, value in data.items():
            setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def deactivate_siblings(
        self, session_id: UUID, entity_type: str, entity_id: Optional[UUID]
    ) -> None:
        """Deactivate all overrides of same entity_type+entity_id in session."""
        conditions = [
            SandboxOverride.session_id == session_id,
            SandboxOverride.entity_type == entity_type,
            SandboxOverride.is_active == True,
        ]
        if entity_id is not None:
            conditions.append(SandboxOverride.entity_id == entity_id)
        else:
            conditions.append(SandboxOverride.entity_id.is_(None))

        stmt = (
            update(SandboxOverride)
            .where(and_(*conditions))
            .values(is_active=False)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete(self, obj: SandboxOverride) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_all_by_session(self, session_id: UUID) -> int:
        stmt = delete(SandboxOverride).where(SandboxOverride.session_id == session_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_active_overrides(self, session_id: UUID) -> List[SandboxOverride]:
        stmt = (
            select(SandboxOverride)
            .where(
                and_(
                    SandboxOverride.session_id == session_id,
                    SandboxOverride.is_active == True,
                )
            )
            .order_by(SandboxOverride.entity_type)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SandboxRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxRun) -> SandboxRun:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, run_id: UUID) -> Optional[SandboxRun]:
        stmt = select(SandboxRun).where(SandboxRun.id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_steps(self, run_id: UUID) -> Optional[SandboxRun]:
        stmt = (
            select(SandboxRun)
            .where(SandboxRun.id == run_id)
            .options(selectinload(SandboxRun.steps))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_session(
        self,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[SandboxRun]:
        stmt = select(SandboxRun).where(SandboxRun.session_id == session_id)
        if branch_id is not None:
            stmt = stmt.where(SandboxRun.branch_id == branch_id)
        stmt = stmt.order_by(SandboxRun.started_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_session_with_steps_count(
        self,
        session_id: UUID,
        branch_id: Optional[UUID] = None,
    ) -> List[Tuple[SandboxRun, int]]:
        """List runs with steps_count in a single query (no N+1)."""
        steps_count_sq = (
            select(
                SandboxRunStep.run_id,
                func.count().label("steps_count"),
            )
            .group_by(SandboxRunStep.run_id)
            .subquery()
        )
        stmt = (
            select(SandboxRun, func.coalesce(steps_count_sq.c.steps_count, 0))
            .outerjoin(steps_count_sq, SandboxRun.id == steps_count_sq.c.run_id)
            .where(SandboxRun.session_id == session_id)
        )
        if branch_id is not None:
            stmt = stmt.where(SandboxRun.branch_id == branch_id)
        stmt = stmt.order_by(SandboxRun.started_at.desc())
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update(self, obj: SandboxRun, data: dict) -> SandboxRun:
        for key, value in data.items():
            setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_steps_count(self, run_id: UUID) -> int:
        stmt = select(func.count()).where(SandboxRunStep.run_id == run_id)
        return await self.session.scalar(stmt) or 0

    async def fail_stale_runs(
        self, session_id: UUID, stale_threshold_minutes: int = 5
    ) -> int:
        """Mark runs stuck in 'running' longer than threshold as failed."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)
        stmt = (
            update(SandboxRun)
            .where(
                and_(
                    SandboxRun.session_id == session_id,
                    SandboxRun.status == "running",
                    SandboxRun.started_at < cutoff,
                )
            )
            .values(
                status="failed",
                error="Execution timed out (stale)",
                finished_at=datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount


class SandboxRunStepRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxRunStep) -> SandboxRunStep:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def bulk_create(self, steps: List[SandboxRunStep]) -> None:
        self.session.add_all(steps)
        await self.session.flush()

    async def list_by_run(self, run_id: UUID) -> List[SandboxRunStep]:
        stmt = (
            select(SandboxRunStep)
            .where(SandboxRunStep.run_id == run_id)
            .order_by(SandboxRunStep.order_num)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SandboxBranchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxBranch) -> SandboxBranch:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, branch_id: UUID) -> Optional[SandboxBranch]:
        stmt = select(SandboxBranch).where(SandboxBranch.id == branch_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_session(self, session_id: UUID) -> List[SandboxBranch]:
        stmt = (
            select(SandboxBranch)
            .where(SandboxBranch.session_id == session_id)
            .order_by(SandboxBranch.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SandboxBranchOverrideRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_branch(self, branch_id: UUID) -> List[SandboxBranchOverride]:
        stmt = (
            select(SandboxBranchOverride)
            .where(SandboxBranchOverride.branch_id == branch_id)
            .order_by(SandboxBranchOverride.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_unique_key(
        self,
        branch_id: UUID,
        entity_type: str,
        entity_id: Optional[UUID],
        field_path: str,
    ) -> Optional[SandboxBranchOverride]:
        stmt = (
            select(SandboxBranchOverride)
            .where(
                and_(
                    SandboxBranchOverride.branch_id == branch_id,
                    SandboxBranchOverride.entity_type == entity_type,
                    SandboxBranchOverride.entity_id == entity_id,
                    SandboxBranchOverride.field_path == field_path,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, obj: SandboxBranchOverride) -> SandboxBranchOverride:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: SandboxBranchOverride, data: dict[str, Any]) -> SandboxBranchOverride:
        for key, value in data.items():
            setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: SandboxBranchOverride) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_entity(
        self,
        branch_id: UUID,
        entity_type: str,
        entity_id: Optional[UUID],
    ) -> int:
        stmt = (
            delete(SandboxBranchOverride)
            .where(
                and_(
                    SandboxBranchOverride.branch_id == branch_id,
                    SandboxBranchOverride.entity_type == entity_type,
                    SandboxBranchOverride.entity_id == entity_id,
                )
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_all_by_branch(self, branch_id: UUID) -> int:
        stmt = delete(SandboxBranchOverride).where(SandboxBranchOverride.branch_id == branch_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)


class SandboxSnapshotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, obj: SandboxOverrideSnapshot) -> SandboxOverrideSnapshot:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, snapshot_id: UUID) -> Optional[SandboxOverrideSnapshot]:
        stmt = select(SandboxOverrideSnapshot).where(SandboxOverrideSnapshot.id == snapshot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
