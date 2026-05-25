from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import app as celery_app
from app.models.periodic_task import PeriodicTask


class PeriodicTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tasks(self, *, category: Optional[str] = None, is_enabled: Optional[bool] = None) -> list[PeriodicTask]:
        stmt = select(PeriodicTask).order_by(PeriodicTask.slug.asc())
        if category:
            stmt = stmt.where(PeriodicTask.category == category)
        if is_enabled is not None:
            stmt = stmt.where(PeriodicTask.is_enabled.is_(is_enabled))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_slug(self, slug: str) -> Optional[PeriodicTask]:
        return (await self.session.execute(select(PeriodicTask).where(PeriodicTask.slug == slug))).scalar_one_or_none()

    async def set_enabled(self, slug: str, is_enabled: bool) -> PeriodicTask | None:
        task = await self.get_by_slug(slug)
        if task is None:
            return None
        task.is_enabled = is_enabled
        await self.session.flush()
        return task

    async def trigger_run(self, slug: str) -> tuple[bool, Optional[str]]:
        task = await self.get_by_slug(slug)
        if task is None or task.is_orphaned:
            return False, None
        async_result = celery_app.send_task(task.task_path, headers={"periodic_manual": "1"})
        task.last_status = "queued"
        task.last_run_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True, str(async_result.id)
