"""
RBAC Admin API — manage RBAC policies and rules.

Architecture:
- RbacPolicy (набор правил) — named collection, CRUD by slug
- RbacRule (правило) — granular resource-level rules within a policy
- check_access — deterministic access check: user → tenant → platform → deny

Not versioned — rules are mutable within a policy.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.rbac_service import (
    RbacService,
    RbacPolicyNotFoundError,
    RbacRuleNotFoundError,
    RbacRuleDuplicateError,
)

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────

class RbacPolicyCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class RbacPolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class RbacPolicyResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    rules_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RbacRuleCreate(BaseModel):
    level: str = Field(..., description="platform | tenant | user")
    level_id: Optional[UUID] = Field(None, description="tenant_id or user_id, NULL for platform")
    resource_type: str = Field(..., description="agent | toolgroup | tool | instance")
    resource_id: UUID
    effect: str = Field(..., description="allow | deny")


class RbacRuleUpdate(BaseModel):
    effect: str = Field(..., description="allow | deny")


class RbacRuleResponse(BaseModel):
    id: UUID
    rbac_policy_id: UUID
    level: str
    level_id: Optional[UUID]
    resource_type: str
    resource_id: UUID
    effect: str
    created_at: datetime
    created_by_user_id: Optional[UUID]

    class Config:
        from_attributes = True


class RbacPolicyDetailResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    rules: List[RbacRuleResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CheckAccessRequest(BaseModel):
    user_id: UUID
    tenant_id: UUID
    resource_type: str
    resource_id: UUID


class CheckAccessResponse(BaseModel):
    effect: str
    resource_type: str
    resource_id: UUID


# ─── Helpers ──────────────────────────────────────────────────────────

def _policy_to_response(policy) -> RbacPolicyResponse:
    return RbacPolicyResponse(
        id=policy.id,
        slug=policy.slug,
        name=policy.name,
        description=policy.description,
        rules_count=len(policy.rules) if policy.rules else 0,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _policy_to_detail(policy) -> RbacPolicyDetailResponse:
    return RbacPolicyDetailResponse(
        id=policy.id,
        slug=policy.slug,
        name=policy.name,
        description=policy.description,
        rules=[RbacRuleResponse.model_validate(r) for r in (policy.rules or [])],
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


# ─── Enriched Rules Response ─────────────────────────────────────────

class EnrichedRulePolicyInfo(BaseModel):
    id: str
    slug: str
    name: str

class EnrichedRuleResourceInfo(BaseModel):
    type: str
    id: str
    name: str

class EnrichedRuleInfo(BaseModel):
    effect: str
    level: str
    level_id: Optional[str] = None
    context_name: Optional[str] = None
    created_at: str
    created_by_user_id: Optional[str] = None

class EnrichedRuleResponse(BaseModel):
    id: str
    policy: EnrichedRulePolicyInfo
    resource: EnrichedRuleResourceInfo
    rule: EnrichedRuleInfo


# ─── Policy Endpoints ────────────────────────────────────────────────

@router.get("/rules", response_model=List[EnrichedRuleResponse])
async def list_enriched_rules(
    rbac_policy_id: Optional[UUID] = Query(None, description="Filter by policy ID"),
    level: Optional[str] = Query(None, description="Filter by level: platform|tenant|user"),
    level_id: Optional[UUID] = Query(None, description="Filter by tenant_id or user_id"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type: agent|toolgroup|tool|instance"),
    effect: Optional[str] = Query(None, description="Filter by effect: allow|deny"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    List all RBAC rules across all policies with enriched data.
    
    Returns flat list with policy info, resource names, and context names.
    Frontend groups/sorts as needed.
    
    Filters:
    - rbac_policy_id: specific policy
    - level: platform|tenant|user
    - level_id: tenant_id or user_id (for tenant/user level rules)
    - resource_type: agent|toolgroup|tool|instance
    - effect: allow|deny
    """
    service = RbacService(db)
    return await service.list_enriched_rules(
        rbac_policy_id=rbac_policy_id,
        level=level,
        level_id=level_id,
        resource_type=resource_type,
        effect=effect,
        skip=skip,
        limit=limit,
    )


@router.get("", response_model=List[RbacPolicyResponse])
async def list_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all RBAC policies."""
    service = RbacService(db)
    policies = await service.list_policies(skip=skip, limit=limit)
    return [_policy_to_response(p) for p in policies]


@router.post("", response_model=RbacPolicyDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: RbacPolicyCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new RBAC policy."""
    try:
        service = RbacService(db)
        policy = await service.create_policy(
            slug=data.slug,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        await db.refresh(policy, attribute_names=["rules"])
        return _policy_to_detail(policy)
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Policy with slug '{data.slug}' already exists")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=RbacPolicyDetailResponse)
async def get_policy(
    slug: str = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get RBAC policy with all rules."""
    try:
        service = RbacService(db)
        policy = await service.get_policy_by_slug(slug)
        return _policy_to_detail(policy)
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")


@router.patch("/{slug}", response_model=RbacPolicyDetailResponse)
async def update_policy(
    data: RbacPolicyUpdate,
    slug: str = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update RBAC policy metadata."""
    try:
        service = RbacService(db)
        policy = await service.update_policy(
            slug=slug,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        await db.refresh(policy, attribute_names=["rules"])
        return _policy_to_detail(policy)
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    slug: str = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete RBAC policy and all its rules."""
    try:
        service = RbacService(db)
        await service.delete_policy(slug)
        await db.commit()
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")


# ─── Rule Endpoints ──────────────────────────────────────────────────

@router.get("/{slug}/rules", response_model=List[RbacRuleResponse])
async def list_rules(
    slug: str = Path(...),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List rules in an RBAC policy."""
    try:
        service = RbacService(db)
        rules = await service.list_rules(slug, level=level, resource_type=resource_type)
        return [RbacRuleResponse.model_validate(r) for r in rules]
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")


@router.post("/{slug}/rules", response_model=RbacRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: RbacRuleCreate,
    slug: str = Path(...),
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Create a new rule in an RBAC policy."""
    try:
        service = RbacService(db)
        rule = await service.create_rule(
            policy_slug=slug,
            level=data.level,
            level_id=data.level_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            effect=data.effect,
            created_by_user_id=UUID(user.id) if user.id else None,
        )
        await db.commit()
        return RbacRuleResponse.model_validate(rule)
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")
    except RbacRuleDuplicateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{slug}/rules/{rule_id}", response_model=RbacRuleResponse)
async def update_rule(
    data: RbacRuleUpdate,
    slug: str = Path(...),
    rule_id: UUID = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a rule's effect (allow ↔ deny)."""
    try:
        service = RbacService(db)
        rule = await service.update_rule(rule_id=rule_id, effect=data.effect)
        await db.commit()
        return RbacRuleResponse.model_validate(rule)
    except RbacRuleNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC rule '{rule_id}' not found")


@router.delete("/{slug}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    slug: str = Path(...),
    rule_id: UUID = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a rule from an RBAC policy."""
    try:
        service = RbacService(db)
        await service.delete_rule(rule_id)
        await db.commit()
    except RbacRuleNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC rule '{rule_id}' not found")


# ─── Access Check ─────────────────────────────────────────────────────

@router.post("/{slug}/check-access", response_model=CheckAccessResponse)
async def check_access(
    data: CheckAccessRequest,
    slug: str = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Check access for a user/tenant to a resource."""
    try:
        service = RbacService(db)
        policy = await service.get_policy_by_slug(slug)
        effect = await service.check_access(
            rbac_policy_id=policy.id,
            user_id=data.user_id,
            tenant_id=data.tenant_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
        )
        return CheckAccessResponse(
            effect=effect,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
        )
    except RbacPolicyNotFoundError:
        raise HTTPException(status_code=404, detail=f"RBAC policy '{slug}' not found")
