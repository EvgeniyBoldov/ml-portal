"""
API endpoints for Agent Runs observability.
Provides listing, detail view, and deletion of agent execution logs.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.models.user import Users
from app.services.run_store import RunStore
from app.schemas.agent_runs import (
    AgentRunResponse,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunStepResponse,
)

router = APIRouter(tags=["Agent Runs"])


@router.get("", response_model=AgentRunListResponse)
async def list_agent_runs(
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    user_id: Optional[UUID] = Query(None, description="Filter by user"),
    chat_id: Optional[UUID] = Query(None, description="Filter by chat"),
    agent_slug: Optional[str] = Query(None, description="Filter by agent"),
    status: Optional[str] = Query(None, description="Filter by status (running, completed, failed)"),
    from_date: Optional[datetime] = Query(None, description="Filter runs after this date"),
    to_date: Optional[datetime] = Query(None, description="Filter runs before this date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(db_session),
    current_user: Users = Depends(require_admin),
):
    """
    List agent runs with optional filters.
    Admin only.
    """
    store = RunStore(session)
    
    runs, total = await store.list_runs(
        tenant_id=tenant_id,
        user_id=user_id,
        chat_id=chat_id,
        agent_slug=agent_slug,
        status=status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    
    return AgentRunListResponse(
        items=[AgentRunResponse.model_validate(run) for run in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
async def get_agent_run(
    run_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: Users = Depends(require_admin),
):
    """
    Get detailed agent run with all steps.
    Admin only.
    """
    store = RunStore(session)
    
    run = await store.get_run_with_steps(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    
    return AgentRunDetailResponse(
        **AgentRunResponse.model_validate(run).model_dump(),
        steps=[AgentRunStepResponse.model_validate(step) for step in run.steps],
    )


@router.delete("/{run_id}")
async def delete_agent_run(
    run_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: Users = Depends(require_admin),
):
    """
    Delete a specific agent run and all its steps.
    Admin only.
    """
    store = RunStore(session)
    
    deleted = await store.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent run not found")
    
    await session.commit()
    
    return {"status": "deleted", "run_id": str(run_id)}


@router.delete("")
async def delete_old_runs(
    before_date: datetime = Query(..., description="Delete runs before this date"),
    tenant_id: Optional[UUID] = Query(None, description="Limit to specific tenant"),
    session: AsyncSession = Depends(db_session),
    current_user: Users = Depends(require_admin),
):
    """
    Bulk delete agent runs older than a given date.
    Admin only.
    """
    store = RunStore(session)
    
    deleted_count = await store.delete_runs_before(before_date, tenant_id)
    await session.commit()
    
    return {
        "status": "deleted",
        "deleted_count": deleted_count,
        "before_date": before_date.isoformat(),
    }


@router.get("/stats/summary")
async def get_runs_stats(
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    from_date: Optional[datetime] = Query(None, description="Stats from this date"),
    to_date: Optional[datetime] = Query(None, description="Stats until this date"),
    session: AsyncSession = Depends(db_session),
    current_user: Users = Depends(require_admin),
):
    """
    Get summary statistics for agent runs.
    Admin only.
    """
    from sqlalchemy import select, func
    from app.models.agent_run import AgentRun
    
    # Base query
    base_filter = []
    if tenant_id:
        base_filter.append(AgentRun.tenant_id == tenant_id)
    if from_date:
        base_filter.append(AgentRun.started_at >= from_date)
    if to_date:
        base_filter.append(AgentRun.started_at <= to_date)
    
    # Total runs
    total_query = select(func.count()).select_from(AgentRun)
    if base_filter:
        total_query = total_query.where(*base_filter)
    total_result = await session.execute(total_query)
    total_runs = total_result.scalar() or 0
    
    # By status
    status_query = (
        select(AgentRun.status, func.count())
        .group_by(AgentRun.status)
    )
    if base_filter:
        status_query = status_query.where(*base_filter)
    status_result = await session.execute(status_query)
    by_status = {row[0]: row[1] for row in status_result.fetchall()}
    
    # By agent
    agent_query = (
        select(AgentRun.agent_slug, func.count())
        .group_by(AgentRun.agent_slug)
        .order_by(func.count().desc())
        .limit(10)
    )
    if base_filter:
        agent_query = agent_query.where(*base_filter)
    agent_result = await session.execute(agent_query)
    by_agent = {row[0]: row[1] for row in agent_result.fetchall()}
    
    # Average duration
    avg_duration_query = select(func.avg(AgentRun.duration_ms)).where(
        AgentRun.duration_ms.isnot(None)
    )
    if base_filter:
        avg_duration_query = avg_duration_query.where(*base_filter)
    avg_result = await session.execute(avg_duration_query)
    avg_duration = avg_result.scalar()
    
    return {
        "total_runs": total_runs,
        "by_status": by_status,
        "by_agent": by_agent,
        "avg_duration_ms": round(avg_duration) if avg_duration else None,
    }
