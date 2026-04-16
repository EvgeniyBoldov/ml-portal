"""Plans API endpoints for managing execution plans."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, db_session, resolve_chat_context, ChatContext
from app.core.security import UserCtx
from app.models.plan import Plan, PlanStatus
from app.schemas.plans import PlanResponse, PlanStatusUpdate
from app.services.plan_service import PlanService

router = APIRouter()


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> Plan:
    """Get plan details by ID."""
    plan_service = PlanService(session)
    plan = await plan_service.get_plan(plan_id)
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check access - user can only access plans from their tenant
    if str(plan.tenant_id) != current_user.tenant_ids[0]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return plan


@router.get("/chats/{chat_id}/plans", response_model=List[PlanResponse])
async def get_chat_plans(
    chat_id: UUID,
    status: Optional[PlanStatus] = Query(None, description="Filter by plan status"),
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(get_current_user),
    chat_ctx: ChatContext = Depends(resolve_chat_context),
) -> List[Plan]:
    """Get all plans for a specific chat."""
    plan_service = PlanService(session)

    plans = await plan_service.get_chat_plans(
        chat_id=chat_id,
        tenant_id=chat_ctx.tenant_id,
        status=status
    )
    
    return plans


@router.get("/agent-runs/{run_id}/plans", response_model=List[PlanResponse])
async def get_run_plans(
    run_id: UUID,
    status: Optional[PlanStatus] = Query(None, description="Filter by plan status"),
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> List[Plan]:
    """Get all plans for a specific agent run."""
    plan_service = PlanService(session)
    
    plans = await plan_service.get_run_plans(
        run_id=run_id,
        tenant_id=current_user.tenant_ids[0],
        status=status
    )
    
    # Verify user has access to these plans
    if plans and str(plans[0].tenant_id) != current_user.tenant_ids[0]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return plans


@router.patch("/plans/{plan_id}/status", response_model=PlanResponse)
async def update_plan_status(
    plan_id: UUID,
    status_update: PlanStatusUpdate,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> Plan:
    """Update plan status."""
    plan_service = PlanService(session)
    
    # Get existing plan
    plan = await plan_service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check access
    if str(plan.tenant_id) != current_user.tenant_ids[0]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update status
    updated_plan = await plan_service.update_plan_status(
        plan_id=plan_id,
        status=status_update.status,
        current_step=status_update.current_step
    )
    
    return updated_plan


@router.post("/plans/{plan_id}/resume", response_model=PlanResponse)
async def resume_plan(
    plan_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> Plan:
    """Resume a paused plan."""
    plan_service = PlanService(session)
    
    # Get existing plan
    plan = await plan_service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check access
    if str(plan.tenant_id) != current_user.tenant_ids[0]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if plan can be resumed
    if plan.status != PlanStatus.PAUSED:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot resume plan with status {plan.status}"
        )
    
    # Resume plan
    resumed_plan = await plan_service.resume_plan(plan_id)
    
    return resumed_plan


@router.post("/plans/{plan_id}/pause", response_model=PlanResponse)
async def pause_plan(
    plan_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> Plan:
    """Pause an active plan."""
    plan_service = PlanService(session)
    
    # Get existing plan
    plan = await plan_service.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Check access
    if str(plan.tenant_id) != current_user.tenant_ids[0]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if plan can be paused
    if plan.status != PlanStatus.ACTIVE:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot pause plan with status {plan.status}"
        )
    
    # Pause plan
    paused_plan = await plan_service.pause_plan(plan_id)
    
    return paused_plan
