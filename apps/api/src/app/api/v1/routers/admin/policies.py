"""
Policies Admin API - text-based rules and restrictions with versioning.

Architecture:
- Policy (container) - holds metadata: slug, name, description
- PolicyVersion - holds versioned data: policy_text, policy_json
- current_version_id - points to the active version

Policy is NOT execution limits (those are in /admin/limits).
Policy defines behavioral rules, restrictions, and guidelines.

Version workflow:
- Create → always draft
- Activate → draft → active (deprecates previous active)
- Deactivate → draft or active → deprecated
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
    slug: str = Field(..., description="Unique slug for this policy")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PolicyVersionCreate(BaseModel):
    policy_text: Optional[str] = Field(None, description="Policy text (inherited from parent if not provided)")
    policy_json: Optional[Dict[str, Any]] = Field(None, description="Structured policy data")
    notes: Optional[str] = Field(None, description="Notes about this version")
    parent_version_id: Optional[UUID] = Field(None, description="Parent version ID for data inheritance")


class PolicyVersionUpdate(BaseModel):
    policy_text: Optional[str] = None
    policy_json: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class PolicyVersionResponse(BaseModel):
    id: UUID
    policy_id: UUID
    version: int
    status: str
    hash: str
    policy_text: str
    policy_json: Optional[Dict[str, Any]] = None
    parent_version_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicyResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    current_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicyDetailResponse(PolicyResponse):
    versions: List[PolicyVersionResponse] = []
    current_version: Optional[PolicyVersionResponse] = None


# ─────────────────────────────────────────────────────────────────────────────
# POLICY CONTAINER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all policies. Admin only."""
    service = PolicyService(db)
    policies, _ = await service.list_policies(skip=skip, limit=limit)
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
        versions = await service.list_versions(slug)

        current = None
        if policy.current_version_id:
            cv = await service.version_repo.get_by_id(policy.current_version_id)
            if cv:
                current = PolicyVersionResponse.model_validate(cv)

        return PolicyDetailResponse(
            id=policy.id,
            slug=policy.slug,
            name=policy.name,
            description=policy.description,
            current_version_id=policy.current_version_id,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
            versions=[PolicyVersionResponse.model_validate(v) for v in versions],
            current_version=current,
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
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, active, deprecated"),
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
            policy_text=data.policy_text,
            policy_json=data.policy_json,
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
            policy_text=data.policy_text,
            policy_json=data.policy_json,
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
    """Delete a version (only draft and deprecated versions). Admin only."""
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
    Deprecates the currently active version.
    Updates current_version_id on the policy.
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
    """Deactivate a version (draft or active → deprecated). Admin only."""
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
