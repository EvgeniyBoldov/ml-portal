from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.periodic_tasks import (
    PeriodicRunDetail,
    PeriodicRunSummary,
    PeriodicTaskDetail,
    PeriodicTaskItem,
    PeriodicTaskListResponse,
    PeriodicTaskRunNowResponse,
    PeriodicTaskToggleRequest,
)
from app.services.periodic_task_service import PeriodicTaskService

router = APIRouter(tags=["periodic-tasks"])


@router.get("", response_model=PeriodicTaskListResponse)
async def list_periodic_tasks(
    category: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = PeriodicTaskService(db)
    items = await service.list_tasks(category=category, is_enabled=is_enabled)
    return PeriodicTaskListResponse(items=[PeriodicTaskItem.model_validate(item) for item in items], total=len(items))


@router.get("/{slug}", response_model=PeriodicTaskDetail)
async def get_periodic_task(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> PeriodicTaskDetail:
    service = PeriodicTaskService(db)
    task = await service.get_by_slug(slug)
    if task is None:
        raise HTTPException(status_code=404, detail="Periodic task not found")
    recent = await service.recent_runs(task)
    return PeriodicTaskDetail(
        **PeriodicTaskItem.model_validate(task).model_dump(),
        runs=[PeriodicRunSummary.model_validate(run) for run in recent],
    )


@router.get("/{slug}/runs/{run_id}", response_model=PeriodicRunDetail)
async def get_periodic_task_run(
    slug: str,
    run_id: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> PeriodicRunDetail:
    service = PeriodicTaskService(db)
    task = await service.get_by_slug(slug)
    run = await service.get_run(task, run_id) if task is not None else None
    if run is None:
        raise HTTPException(status_code=404, detail="Periodic task run not found")
    return PeriodicRunDetail.model_validate(run)


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
