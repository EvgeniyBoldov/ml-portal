"""
Policies Admin API - with versioning support.

Architecture:
- Policy (container) - holds metadata: slug, name, description
- PolicyVersion - holds versioned data: limits, timeouts, budgets
- recommended_version_id - points to the version that should be used by default

Version workflow:
- Create → always draft
- Activate → draft → active (deactivates previous active)
- Deactivate → draft or active → inactive
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.policy_service import (
    PolicyService,
    PolicyError,
    PolicyNotFoundError,
    PolicyVersionNotFoundError,
    PolicyAlreadyExistsError,
    PolicyVersionNotEditableError,
)

router = APIRouter(tags=["policies"])


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    """Schema for creating a policy container"""
    slug: str = Field(..., description="Unique slug for this policy")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None


class PolicyUpdate(BaseModel):
    """Schema for updating a policy container"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PolicyVersionCreate(BaseModel):
    """Schema for creating a policy version"""
    max_steps: Optional[int] = Field(None, description="Maximum agent steps")
    max_tool_calls: Optional[int] = Field(None, description="Maximum tool calls")
    max_wall_time_ms: Optional[int] = Field(None, description="Maximum wall time in ms")
    tool_timeout_ms: Optional[int] = Field(None, description="Tool timeout in ms")
    max_retries: Optional[int] = Field(None, description="Maximum retries")
    budget_tokens: Optional[int] = Field(None, description="Token budget")
    budget_cost_cents: Optional[int] = Field(None, description="Cost budget in cents")
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = Field(None, description="Notes about this version")
    parent_version_id: Optional[UUID] = Field(None, description="Parent version ID")


class PolicyVersionUpdate(BaseModel):
    """Schema for updating a policy version (only draft)"""
    max_steps: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_wall_time_ms: Optional[int] = None
    tool_timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    budget_tokens: Optional[int] = None
    budget_cost_cents: Optional[int] = None
    extra_config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class PolicyVersionResponse(BaseModel):
    """Schema for policy version response"""
    id: UUID
    policy_id: UUID
    version: int
    status: str
    max_steps: Optional[int]
    max_tool_calls: Optional[int]
    max_wall_time_ms: Optional[int]
    tool_timeout_ms: Optional[int]
    max_retries: Optional[int]
    budget_tokens: Optional[int]
    budget_cost_cents: Optional[int]
    extra_config: Dict[str, Any]
    parent_version_id: Optional[UUID]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicyResponse(BaseModel):
    """Schema for policy container response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    recommended_version_id: Optional[UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicyDetailResponse(PolicyResponse):
    """Schema for policy with versions"""
    versions: List[PolicyVersionResponse] = []
    recommended_version: Optional[PolicyVersionResponse] = None


# ─────────────────────────────────────────────────────────────────────────────
# POLICY CONTAINER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

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
    """Create a new policy container. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.create_policy(
            slug=data.slug,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        return policy
    except PolicyAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=PolicyDetailResponse)
async def get_policy(
    slug: str = Path(..., description="Policy slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get policy by slug with all versions. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.get_policy_with_versions(slug)
        
        # Build response with versions
        versions = await service.list_versions(slug)
        recommended = await service.get_recommended_version(slug)
        
        return PolicyDetailResponse(
            id=policy.id,
            slug=policy.slug,
            name=policy.name,
            description=policy.description,
            recommended_version_id=policy.recommended_version_id,
            is_active=policy.is_active,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
            versions=[PolicyVersionResponse.model_validate(v) for v in versions],
            recommended_version=PolicyVersionResponse.model_validate(recommended) if recommended else None,
        )
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{slug}", response_model=PolicyResponse)
async def update_policy(
    data: PolicyUpdate,
    slug: str = Path(..., description="Policy slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update policy container metadata. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.get_policy_by_slug(slug)
        policy = await service.update_policy(
            policy_id=policy.id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        await db.commit()
        return policy
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    slug: str = Path(..., description="Policy slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete policy and all its versions. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.get_policy_by_slug(slug)
        await service.delete_policy(policy.id)
        await db.commit()
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POLICY VERSION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{slug}/versions", response_model=List[PolicyVersionResponse])
async def list_versions(
    slug: str = Path(..., description="Policy slug"),
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, active, inactive"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all versions of a policy. Admin only."""
    service = PolicyService(db)
    try:
        versions = await service.list_versions(slug, status_filter)
        return versions
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{slug}/versions", response_model=PolicyVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    data: PolicyVersionCreate,
    slug: str = Path(..., description="Policy slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new version for a policy (always in draft status). Admin only."""
    service = PolicyService(db)
    try:
        version = await service.create_version(
            policy_slug=slug,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            budget_tokens=data.budget_tokens,
            budget_cost_cents=data.budget_cost_cents,
            extra_config=data.extra_config,
            notes=data.notes,
            parent_version_id=data.parent_version_id,
        )
        await db.commit()
        return version
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}/versions/{version_number}", response_model=PolicyVersionResponse)
async def get_version(
    slug: str = Path(..., description="Policy slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get specific version of a policy. Admin only."""
    service = PolicyService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        return version
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}/versions/{version_number}", response_model=PolicyVersionResponse)
async def update_version(
    data: PolicyVersionUpdate,
    slug: str = Path(..., description="Policy slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a version (only draft versions can be edited). Admin only."""
    service = PolicyService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.update_version(
            version_id=version.id,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            budget_tokens=data.budget_tokens,
            budget_cost_cents=data.budget_cost_cents,
            extra_config=data.extra_config,
            notes=data.notes,
        )
        await db.commit()
        return version
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyVersionNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}/versions/{version_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    slug: str = Path(..., description="Policy slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a version (only draft and inactive versions can be deleted). Admin only."""
    service = PolicyService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        await service.delete_version(version.id)
        await db.commit()
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/activate", response_model=PolicyVersionResponse)
async def activate_version(
    slug: str = Path(..., description="Policy slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Activate a version (draft → active).
    Deactivates the currently active version (active → inactive).
    Updates recommended_version_id on the policy.
    Admin only.
    """
    service = PolicyService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.activate_version(version.id)
        await db.commit()
        return version
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/deactivate", response_model=PolicyVersionResponse)
async def deactivate_version(
    slug: str = Path(..., description="Policy slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Deactivate a version (draft or active → inactive). Admin only."""
    service = PolicyService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.deactivate_version(version.id)
        await db.commit()
        return version
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}/recommended", response_model=PolicyVersionResponse)
async def get_recommended_version(
    slug: str = Path(..., description="Policy slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get the recommended version for a policy. Admin only."""
    service = PolicyService(db)
    try:
        version = await service.get_recommended_version(slug)
        if not version:
            raise HTTPException(status_code=404, detail="No recommended version found")
        return version
    except PolicyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{slug}/recommended", response_model=PolicyResponse)
async def set_recommended_version(
    slug: str = Path(..., description="Policy slug"),
    version_id: UUID = Query(..., description="Version ID to set as recommended"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Set the recommended version for a policy. Admin only."""
    service = PolicyService(db)
    try:
        policy = await service.update_recommended_version(slug, version_id)
        await db.commit()
        return policy
    except (PolicyNotFoundError, PolicyVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
