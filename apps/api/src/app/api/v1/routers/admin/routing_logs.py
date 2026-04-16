"""
Routing Logs Admin API
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.repositories.routing_log_repository import RoutingLogRepository
from app.schemas.routing_logs import RoutingLogResponse

router = APIRouter(tags=["routing-logs"])


@router.get("", response_model=List[RoutingLogResponse])
async def list_routing_logs(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[UUID] = Query(None, description="Filter by user"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    agent_slug: Optional[str] = Query(None, description="Filter by agent"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List routing logs. Admin only."""
    repo = RoutingLogRepository(db)
    logs, _ = await repo.list_logs(
        skip=skip,
        limit=limit,
        user_id=user_id,
        tenant_id=tenant_id,
        agent_slug=agent_slug,
        status=status_filter,
    )
    return logs


@router.get("/stats")
async def get_routing_stats(
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    since: Optional[datetime] = Query(None, description="Stats since datetime"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get routing statistics. Admin only."""
    repo = RoutingLogRepository(db)
    return await repo.get_stats(tenant_id=tenant_id, since=since)


@router.get("/{log_id}", response_model=RoutingLogResponse)
async def get_routing_log(
    log_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get routing log by ID. Admin only."""
    repo = RoutingLogRepository(db)
    log = await repo.get_by_id(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Routing log not found")
    return log


@router.get("/run/{run_id}", response_model=RoutingLogResponse)
async def get_routing_log_by_run(
    run_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get routing log by run ID. Admin only."""
    repo = RoutingLogRepository(db)
    log = await repo.get_by_run_id(run_id)
    if not log:
        raise HTTPException(status_code=404, detail="Routing log not found")
    return log
