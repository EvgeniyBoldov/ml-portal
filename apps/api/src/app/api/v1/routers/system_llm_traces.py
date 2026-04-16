"""
API endpoints for SystemLLMTrace management.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, UserCtx
from app.models.system_llm_trace import SystemLLMTraceType
from app.services.system_llm_trace_service import SystemLLMTraceService
from app.schemas.system_llm_traces import (
    SystemLLMTraceResponse,
    SystemLLMTraceListResponse,
    TraceStatisticsResponse
)

router = APIRouter(prefix="/system-llm-traces", tags=["system-llm-traces"])


@router.get("/{trace_id}", response_model=SystemLLMTraceResponse)
async def get_trace(
    trace_id: str,
    session: AsyncSession = Depends(db_session),
    user_ctx: UserCtx = Depends()
) -> SystemLLMTraceResponse:
    """Get a specific LLM trace by ID."""
    trace_service = SystemLLMTraceService(session)
    
    try:
        trace = await trace_service.get_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")
        
        # Check tenant access
        if trace.tenant_id and trace.tenant_id != user_ctx.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return SystemLLMTraceResponse.model_validate(trace)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/chat/{chat_id}", response_model=SystemLLMTraceListResponse)
async def get_chat_traces(
    chat_id: str,
    trace_type: Optional[str] = Query(None, description="Filter by trace type"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of traces to return"),
    session: AsyncSession = Depends(db_session),
    user_ctx: UserCtx = Depends()
) -> SystemLLMTraceListResponse:
    """Get all traces for a specific chat."""
    trace_service = SystemLLMTraceService(session)
    
    try:
        traces = await trace_service.get_chat_traces(
            chat_id=chat_id,
            trace_type=trace_type,
            limit=limit
        )
        
        # Filter by tenant
        traces = [t for t in traces if not t.tenant_id or t.tenant_id == user_ctx.tenant_id]
        
        return SystemLLMTraceListResponse(
            traces=[SystemLLMTraceResponse.model_validate(t) for t in traces],
            total=len(traces)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/statistics", response_model=TraceStatisticsResponse)
async def get_trace_statistics(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    trace_type: Optional[str] = Query(None, description="Filter by trace type"),
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    session: AsyncSession = Depends(db_session),
    user_ctx: UserCtx = Depends()
) -> TraceStatisticsResponse:
    """Get trace statistics for analysis."""
    trace_service = SystemLLMTraceService(session)
    
    # Use user's tenant if not specified
    target_tenant_id = tenant_id or str(user_ctx.tenant_id)
    
    try:
        stats = await trace_service.get_trace_statistics(
            tenant_id=target_tenant_id,
            trace_type=trace_type,
            days=days
        )
        
        return TraceStatisticsResponse(
            tenant_id=target_tenant_id,
            trace_type=trace_type,
            days=days,
            statistics=stats
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/cleanup")
async def cleanup_old_traces(
    days: int = Query(14, ge=1, le=365, description="Delete traces older than this many days"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    session: AsyncSession = Depends(db_session),
    user_ctx: UserCtx = Depends()
) -> dict:
    """Clean up old traces (admin only)."""
    # Check admin permissions
    if not user_ctx.has_role("admin") and not user_ctx.has_role("tenant_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    trace_service = SystemLLMTraceService(session)
    
    # Use user's tenant if not specified (for tenant_admin)
    target_tenant_id = tenant_id or str(user_ctx.tenant_id)
    
    try:
        deleted_count = await trace_service.cleanup_old_traces(
            days=days,
            tenant_id=target_tenant_id
        )
        
        return {
            "deleted_count": deleted_count,
            "days": days,
            "tenant_id": target_tenant_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/recent", response_model=SystemLLMTraceListResponse)
async def get_recent_traces(
    trace_type: Optional[str] = Query(None, description="Filter by trace type"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of traces to return"),
    session: AsyncSession = Depends(db_session),
    user_ctx: UserCtx = Depends()
) -> SystemLLMTraceListResponse:
    """Get recent traces for the current tenant."""
    trace_service = SystemLLMTraceService(session)
    
    try:
        traces = await trace_service.get_recent_traces(
            tenant_id=str(user_ctx.tenant_id),
            trace_type=trace_type,
            limit=limit
        )
        
        return SystemLLMTraceListResponse(
            traces=[SystemLLMTraceResponse.model_validate(t) for t in traces],
            total=len(traces)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
