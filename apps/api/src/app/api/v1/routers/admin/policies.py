"""
Policies Admin API
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.policy_service import (
    PolicyService,
    PolicyError,
    PolicyNotFoundError,
    PolicyAlreadyExistsError,
)

router = APIRouter(tags=["policies"])


class PolicyCreate(BaseModel):
    """Schema for creating a policy"""
    slug: str = Field(..., description="Unique slug for this policy")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    max_steps: Optional[int] = Field(None, description="Maximum agent steps")
    max_tool_calls: Optional[int] = Field(None, description="Maximum tool calls")
    max_wall_time_ms: Optional[int] = Field(None, description="Maximum wall time in ms")
    tool_timeout_ms: Optional[int] = Field(None, description="Tool timeout in ms")
    max_retries: Optional[int] = Field(None, description="Maximum retries")
    budget_tokens: Optional[int] = Field(None, description="Token budget")
    budget_cost_cents: Optional[int] = Field(None, description="Cost budget in cents")
    extra_config: Dict[str, Any] = Field(default_factory=dict)


class PolicyUpdate(BaseModel):
    """Schema for updating a policy"""
    name: Optional[str] = None
    description: Optional[str] = None
    max_steps: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_wall_time_ms: Optional[int] = None
    tool_timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    budget_tokens: Optional[int] = None
    budget_cost_cents: Optional[int] = None
    extra_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PolicyResponse(BaseModel):
    """Schema for policy response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    max_steps: Optional[int]
    max_tool_calls: Optional[int]
    max_wall_time_ms: Optional[int]
    tool_timeout_ms: Optional[int]
    max_retries: Optional[int]
    budget_tokens: Optional[int]
    budget_cost_cents: Optional[int]
    extra_config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all policies. Admin only."""
    service = PolicyService(db)
    policies, _ = await service.list_policies(
        skip=skip,
        limit=limit,
        is_active=is_active,
    )
    return policies


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new policy. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.create_policy(
            slug=data.slug,
            name=data.name,
            description=data.description,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            budget_tokens=data.budget_tokens,
            budget_cost_cents=data.budget_cost_cents,
            extra_config=data.extra_config,
        )
        await db.commit()
        return policy
    except PolicyAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get policy by ID. Admin only."""
    service = PolicyService(db)
    try:
        return await service.get_policy(policy_id)
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update policy. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.update_policy(
            policy_id=policy_id,
            name=data.name,
            description=data.description,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            budget_tokens=data.budget_tokens,
            budget_cost_cents=data.budget_cost_cents,
            extra_config=data.extra_config,
            is_active=data.is_active,
        )
        await db.commit()
        return policy
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete policy. Admin only."""
    service = PolicyService(db)
    try:
        await service.delete_policy(policy_id)
        await db.commit()
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
