"""
RBAC Admin API v3 — flat rule management (no policy container).

Architecture:
- RbacRule — granular resource-level rules with direct owner binding
- Owner: user_id | tenant_id | platform
- check_access — deterministic: user → tenant → platform → deny
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.rbac_service import RbacService
from app.schemas.rbac import (
    RbacRuleCreate,
    RbacRuleUpdate,
    RbacRuleResponse,
    CheckAccessRequest,
    CheckAccessResponse,
    EnrichedRuleResponse,
)

router = APIRouter()


# ─── Rule Endpoints ──────────────────────────────────────────────────

@router.get("/rules", response_model=List[EnrichedRuleResponse])
async def list_enriched_rules(
    level: Optional[str] = Query(None, description="Filter by level: platform|tenant|user"),
    owner_user_id: Optional[UUID] = Query(None, description="Filter by owner user_id"),
    owner_tenant_id: Optional[UUID] = Query(None, description="Filter by owner tenant_id"),
    owner_platform: Optional[bool] = Query(None, description="Filter platform rules"),
    resource_type: Optional[str] = Query(None, description="Filter: agent|tool|instance"),
    resource_id: Optional[UUID] = Query(None, description="Filter by resource id"),
    effect: Optional[str] = Query(None, description="Filter: allow|deny"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    List all RBAC rules with enriched data (owner names, resource names).
    """
    service = RbacService(db)
    return await service.list_enriched_rules(
        level=level,
        owner_user_id=owner_user_id,
        owner_tenant_id=owner_tenant_id,
        owner_platform=owner_platform,
        resource_type=resource_type,
        resource_id=resource_id,
        effect=effect,
        skip=skip,
        limit=limit,
    )


@router.get("", response_model=List[RbacRuleResponse])
async def list_rules(
    level: Optional[str] = Query(None),
    owner_user_id: Optional[UUID] = Query(None),
    owner_tenant_id: Optional[UUID] = Query(None),
    owner_platform: Optional[bool] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[UUID] = Query(None),
    effect: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List RBAC rules with filters."""
    service = RbacService(db)
    rules = await service.list_rules(
        level=level,
        owner_user_id=owner_user_id,
        owner_tenant_id=owner_tenant_id,
        owner_platform=owner_platform,
        resource_type=resource_type,
        resource_id=resource_id,
        effect=effect,
        skip=skip,
        limit=limit,
    )
    return [RbacRuleResponse.model_validate(r) for r in rules]


@router.post("", response_model=RbacRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: RbacRuleCreate,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Create a new RBAC rule with direct owner binding."""
    service = RbacService(db)
    rule = await service.create_rule(
        level=data.level,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
        effect=data.effect,
        owner_user_id=data.owner_user_id,
        owner_tenant_id=data.owner_tenant_id,
        owner_platform=data.owner_platform,
        created_by_user_id=UUID(user.id) if user.id else None,
    )
    await db.commit()
    return RbacRuleResponse.model_validate(rule)


@router.get("/{rule_id}", response_model=RbacRuleResponse)
async def get_rule(
    rule_id: UUID = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get a specific RBAC rule."""
    service = RbacService(db)
    rule = await service.get_rule(rule_id)
    return RbacRuleResponse.model_validate(rule)


@router.patch("/{rule_id}", response_model=RbacRuleResponse)
async def update_rule(
    data: RbacRuleUpdate,
    rule_id: UUID = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a rule's effect (allow ↔ deny)."""
    service = RbacService(db)
    rule = await service.update_rule(rule_id=rule_id, effect=data.effect)
    await db.commit()
    return RbacRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID = Path(...),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete an RBAC rule."""
    service = RbacService(db)
    await service.delete_rule(rule_id)
    await db.commit()


# ─── Access Check ─────────────────────────────────────────────────────

@router.post("/check-access", response_model=CheckAccessResponse)
async def check_access(
    data: CheckAccessRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Check access for a user/tenant to a resource (user → tenant → platform → deny)."""
    service = RbacService(db)
    effect = await service.check_access(
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
