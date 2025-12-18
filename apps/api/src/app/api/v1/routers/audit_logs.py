"""
Audit Logs endpoints for admin observability.

Provides read-only access to MCP and API audit logs.
"""
from __future__ import annotations
import logging
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[str]
    tenant_id: Optional[str]
    action: str
    resource: Optional[str]
    request_data: Optional[dict]
    response_status: str
    response_data: Optional[dict]
    error_message: Optional[str]
    duration_ms: Optional[int]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int


class AuditLogStats(BaseModel):
    total_requests: int
    success_count: int
    error_count: int
    avg_duration_ms: Optional[float]
    total_tokens_in: int
    total_tokens_out: int
    top_actions: List[dict]
    top_users: List[dict]


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
):
    """
    List audit logs with filtering and pagination.
    
    Admin only.
    """
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    
    # Apply filters
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
        count_query = count_query.where(AuditLog.action.ilike(f"%{action}%"))
    
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    
    if status:
        query = query.where(AuditLog.response_status == status)
        count_query = count_query.where(AuditLog.response_status == status)
    
    if from_date:
        query = query.where(AuditLog.created_at >= from_date)
        count_query = count_query.where(AuditLog.created_at >= from_date)
    
    if to_date:
        query = query.where(AuditLog.created_at <= to_date)
        count_query = count_query.where(AuditLog.created_at <= to_date)
    
    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size)
    
    result = await session.execute(query)
    items = list(result.scalars().all())
    
    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=AuditLogStats)
async def get_audit_stats(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
):
    """
    Get audit log statistics.
    
    Admin only.
    """
    base_query = select(AuditLog)
    
    if from_date:
        base_query = base_query.where(AuditLog.created_at >= from_date)
    if to_date:
        base_query = base_query.where(AuditLog.created_at <= to_date)
    
    # Total requests
    total_result = await session.execute(
        select(func.count(AuditLog.id)).select_from(base_query.subquery())
    )
    total_requests = total_result.scalar() or 0
    
    # Success/error counts
    success_result = await session.execute(
        select(func.count(AuditLog.id))
        .where(AuditLog.response_status == "success")
    )
    success_count = success_result.scalar() or 0
    error_count = total_requests - success_count
    
    # Average duration
    avg_result = await session.execute(
        select(func.avg(AuditLog.duration_ms))
    )
    avg_duration_ms = avg_result.scalar()
    
    # Total tokens
    tokens_result = await session.execute(
        select(
            func.coalesce(func.sum(AuditLog.tokens_in), 0),
            func.coalesce(func.sum(AuditLog.tokens_out), 0),
        )
    )
    tokens_row = tokens_result.one()
    total_tokens_in = tokens_row[0]
    total_tokens_out = tokens_row[1]
    
    # Top actions
    top_actions_result = await session.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("count"))
        .group_by(AuditLog.action)
        .order_by(desc("count"))
        .limit(10)
    )
    top_actions = [{"action": row[0], "count": row[1]} for row in top_actions_result.all()]
    
    # Top users
    top_users_result = await session.execute(
        select(AuditLog.user_id, func.count(AuditLog.id).label("count"))
        .where(AuditLog.user_id.isnot(None))
        .group_by(AuditLog.user_id)
        .order_by(desc("count"))
        .limit(10)
    )
    top_users = [{"user_id": row[0], "count": row[1]} for row in top_users_result.all()]
    
    return AuditLogStats(
        total_requests=total_requests,
        success_count=success_count,
        error_count=error_count,
        avg_duration_ms=float(avg_duration_ms) if avg_duration_ms else None,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        top_actions=top_actions,
        top_users=top_users,
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get a single audit log entry.
    
    Admin only.
    """
    result = await session.execute(
        select(AuditLog).where(AuditLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Audit log not found")
    
    return log
