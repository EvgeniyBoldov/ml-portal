from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.periodic_task import PeriodicTask, PeriodicTaskRun


class PeriodicTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tasks(self, *, category: str | None, is_enabled: bool | None) -> list[PeriodicTask]:
        stmt = select(PeriodicTask).order_by(PeriodicTask.name, PeriodicTask.slug)
        if category:
            stmt = stmt.where(PeriodicTask.category == category)
        if is_enabled is not None:
            stmt = stmt.where(PeriodicTask.is_enabled.is_(is_enabled))
        return list(await self.session.scalars(stmt))

    async def get_task(self, slug: str, *, lock: bool = False) -> PeriodicTask | None:
        stmt = select(PeriodicTask).where(PeriodicTask.slug == slug)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    async def get_run(self, task_id: UUID, run_id: str) -> PeriodicTaskRun | None:
        return await self.session.scalar(
            select(PeriodicTaskRun).where(PeriodicTaskRun.task_id == task_id, PeriodicTaskRun.id == run_id)
        )

    def add_run(self, run: PeriodicTaskRun) -> None:
        self.session.add(run)

    async def list_runs(self, task_id: UUID, *, limit: int) -> list[PeriodicTaskRun]:
        stmt = (
            select(PeriodicTaskRun)
            .where(PeriodicTaskRun.task_id == task_id)
            .order_by(PeriodicTaskRun.created_at.desc(), PeriodicTaskRun.id.desc())
            .options(defer(PeriodicTaskRun.events), defer(PeriodicTaskRun.result), defer(PeriodicTaskRun.error))
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))

    async def prune_runs(self, task_id: UUID, *, keep: int) -> None:
        recent = (
            select(PeriodicTaskRun.id)
            .where(PeriodicTaskRun.task_id == task_id)
            .order_by(PeriodicTaskRun.created_at.desc(), PeriodicTaskRun.id.desc())
            .limit(keep)
        )
        await self.session.execute(
            delete(PeriodicTaskRun).where(PeriodicTaskRun.task_id == task_id, PeriodicTaskRun.id.not_in(recent))
        )
