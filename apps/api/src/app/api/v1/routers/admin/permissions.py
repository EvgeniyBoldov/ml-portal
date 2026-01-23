"""
Permissions Admin API
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.permission_service import PermissionService
from app.repositories.permission_set_repository import PermissionSetRepository
from app.schemas.tool_instances import (
    PermissionSetCreate,
    PermissionSetUpdate,
    PermissionSetResponse,
    EffectivePermissionsResponse,
)

router = APIRouter(tags=["permissions"])


@router.get("", response_model=List[PermissionSetResponse])
async def list_permission_sets(
    skip: int = 0,
    limit: int = 100,
    scope: Optional[str] = Query(None, description="Filter by scope"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all permission sets. Admin only."""
    repo = PermissionSetRepository(db)
    perm_sets, _ = await repo.list_permission_sets(
        skip=skip,
        limit=limit,
        scope=scope,
        tenant_id=tenant_id,
    )
    return perm_sets


@router.post("", response_model=PermissionSetResponse, status_code=status.HTTP_201_CREATED)
async def create_permission_set(
    data: PermissionSetCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new permission set. Admin only."""
    from app.models.permission_set import PermissionSet
    
    repo = PermissionSetRepository(db)
    
    perm_set = PermissionSet(
        scope=data.scope,
        tenant_id=data.tenant_id,
        user_id=data.user_id,
        allowed_tools=data.allowed_tools,
        denied_tools=data.denied_tools,
        allowed_collections=data.allowed_collections,
        denied_collections=data.denied_collections,
    )
    
    try:
        result = await repo.create(perm_set)
        await db.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/effective", response_model=EffectivePermissionsResponse)
async def get_effective_permissions(
    user_id: Optional[UUID] = Query(None, description="User ID"),
    tenant_id: Optional[UUID] = Query(None, description="Tenant ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get effective (resolved) permissions for user/tenant context. Admin only."""
    service = PermissionService(db)
    perms = await service.resolve_permissions(user_id=user_id, tenant_id=tenant_id)
    return EffectivePermissionsResponse(
        allowed_tools=list(perms.allowed_tools),
        denied_tools=list(perms.denied_tools),
        allowed_collections=list(perms.allowed_collections),
        denied_collections=list(perms.denied_collections),
    )


@router.get("/{perm_id}", response_model=PermissionSetResponse)
async def get_permission_set(
    perm_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get permission set by ID. Admin only."""
    repo = PermissionSetRepository(db)
    perm_set = await repo.get_by_id(perm_id)
    if not perm_set:
        raise HTTPException(status_code=404, detail="Permission set not found")
    return perm_set


@router.put("/{perm_id}", response_model=PermissionSetResponse)
async def update_permission_set(
    perm_id: UUID,
    data: PermissionSetUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update permission set. Admin only."""
    repo = PermissionSetRepository(db)
    perm_set = await repo.get_by_id(perm_id)
    if not perm_set:
        raise HTTPException(status_code=404, detail="Permission set not found")
    
    if data.allowed_tools is not None:
        perm_set.allowed_tools = data.allowed_tools
    if data.denied_tools is not None:
        perm_set.denied_tools = data.denied_tools
    if data.allowed_collections is not None:
        perm_set.allowed_collections = data.allowed_collections
    if data.denied_collections is not None:
        perm_set.denied_collections = data.denied_collections
    
    result = await repo.update(perm_set)
    await db.commit()
    return result


@router.delete("/{perm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission_set(
    perm_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete permission set. Admin only."""
    repo = PermissionSetRepository(db)
    perm_set = await repo.get_by_id(perm_id)
    if not perm_set:
        raise HTTPException(status_code=404, detail="Permission set not found")
    
    await repo.delete(perm_set)
    await db.commit()
