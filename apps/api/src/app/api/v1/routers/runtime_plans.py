"""Read-only projection of the canonical Runtime V3 execution graph."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.security import UserCtx
from app.models.runtime_plan import RuntimePlan, RuntimePlanTask
from app.models.runtime_observability import RuntimeExecutionEvent
from app.schemas.runtime_plans import RuntimePlanView, RuntimeEventView, RuntimeTimelineView

router = APIRouter(prefix="/runtime")


async def _load_plan(plan_id: UUID, session: AsyncSession, current_user: UserCtx) -> RuntimePlanView:
    result = await session.execute(select(RuntimePlan).where(RuntimePlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Runtime plan not found")
    if str(plan.tenant_id) not in current_user.tenant_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    tasks = await session.execute(
        select(RuntimePlanTask).where(RuntimePlanTask.plan_id == plan.id).order_by(RuntimePlanTask.created_at)
    )
    return RuntimePlanView.model_validate({
        **{column.name: getattr(plan, column.name) for column in RuntimePlan.__table__.columns},
        "tasks": list(tasks.scalars().all()),
    })


@router.get("/plans/{plan_id}", response_model=RuntimePlanView)
async def get_runtime_plan(
    plan_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> RuntimePlanView:
    return await _load_plan(plan_id, session, current_user)


@router.get("/runs/{run_id}/plan", response_model=RuntimePlanView)
async def get_runtime_run_plan(
    run_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> RuntimePlanView:
    result = await session.execute(select(RuntimePlan).where(RuntimePlan.root_run_id == run_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Runtime plan not found")
    return await _load_plan(plan.id, session, current_user)


@router.get("/runs/{run_id}/events", response_model=List[RuntimeEventView])
async def get_runtime_run_events(
    run_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> List[RuntimeEventView]:
    plan = await session.scalar(select(RuntimePlan).where(RuntimePlan.root_run_id == run_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="Runtime plan not found")
    if str(plan.tenant_id) not in current_user.tenant_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await session.execute(select(RuntimeExecutionEvent).where(
        RuntimeExecutionEvent.run_id == run_id
    ).order_by(RuntimeExecutionEvent.sequence))
    return [RuntimeEventView.model_validate(row) for row in result.scalars().all()]


@router.get("/runs/{run_id}/timeline", response_model=RuntimeTimelineView)
async def get_runtime_run_timeline(
    run_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> RuntimeTimelineView:
    """Return plan snapshot and ordered canonical events for one run.

    The endpoint is intentionally a read projection: event persistence remains
    append-only and the frontend owns only presentation state.
    """
    plan = await session.scalar(select(RuntimePlan).where(RuntimePlan.root_run_id == run_id))
    if plan is not None:
        if str(plan.tenant_id) not in current_user.tenant_ids:
            raise HTTPException(status_code=403, detail="Access denied")
        plan_view = await _load_plan(plan.id, session, current_user)
    else:
        raise HTTPException(status_code=404, detail="Runtime plan not found")

    result = await session.execute(
        select(RuntimeExecutionEvent)
        .where(RuntimeExecutionEvent.run_id == run_id)
        .order_by(RuntimeExecutionEvent.sequence)
    )
    return RuntimeTimelineView(
        run_id=run_id,
        plan=plan_view,
        events=[RuntimeEventView.model_validate(row) for row in result.scalars().all()],
    )
