from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.periodic_tasks import (
    PeriodicTaskItem,
    PeriodicTaskListResponse,
    PeriodicTaskRunNowResponse,
    PeriodicTaskToggleRequest,
)
from app.services.periodic_task_service import PeriodicTaskService
from app.services.periodic_task_sync_service import PeriodicTaskSyncService

router = APIRouter(tags=["periodic-tasks"])


@router.get("", response_model=PeriodicTaskListResponse)
async def list_periodic_tasks(
    category: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
): 
    await PeriodicTaskSyncService(db).sync_from_beat()
    await db.commit()
    service = PeriodicTaskService(db)
    items = await service.list_tasks(category=category, is_enabled=is_enabled)
    return PeriodicTaskListResponse(items=[PeriodicTaskItem.model_validate(item) for item in items], total=len(items))


@router.patch("/{slug}", response_model=PeriodicTaskItem)
async def toggle_periodic_task(
    slug: str,
    payload: PeriodicTaskToggleRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = PeriodicTaskService(db)
    task = await service.set_enabled(slug, payload.is_enabled)
    if task is None:
        raise HTTPException(status_code=404, detail="Periodic task not found")
    await db.commit()
    await db.refresh(task)
    return PeriodicTaskItem.model_validate(task)


@router.post("/{slug}/run", response_model=PeriodicTaskRunNowResponse)
async def run_periodic_task_now(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = PeriodicTaskService(db)
    queued, task_id = await service.trigger_run(slug)
    if not queued:
        raise HTTPException(status_code=404, detail="Periodic task not found or orphaned")
    await db.commit()
    return PeriodicTaskRunNowResponse(slug=slug, queued=True, task_id=task_id)
