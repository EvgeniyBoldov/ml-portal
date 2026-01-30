"""
Credentials Admin API
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.credential_service import (
    CredentialService,
    CredentialError,
    CredentialNotFoundError,
    CredentialExistsError,
)
from app.schemas.tool_instances import (
    CredentialSetCreate,
    CredentialSetUpdate,
    CredentialSetResponse,
)

router = APIRouter(tags=["credentials"])


@router.get("", response_model=List[CredentialSetResponse])
async def list_credentials(
    skip: int = 0,
    limit: int = 100,
    tool_instance_id: Optional[UUID] = Query(None, description="Filter by tool instance"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all credential sets. Admin only."""
    service = CredentialService(db)
    creds, _ = await service.list_credentials(
        skip=skip,
        limit=limit,
        tool_instance_id=tool_instance_id,
        scope=scope,
        tenant_id=tenant_id,
        is_active=is_active,
    )
    return creds


@router.post("", response_model=CredentialSetResponse, status_code=status.HTTP_201_CREATED)
async def create_credentials(
    data: CredentialSetCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new credentials. Admin only. Scope can be 'default', 'tenant', or 'user'."""
    service = CredentialService(db)
    try:
        cred_set = await service.create_credentials(
            tool_instance_id=data.tool_instance_id,
            auth_type=data.auth_type,
            payload=data.payload,
            scope=data.scope,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            is_default=data.is_default,
        )
        await db.commit()
        return cred_set
    except CredentialExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CredentialError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{credential_id}", response_model=CredentialSetResponse)
async def get_credentials(
    credential_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get credential set by ID. Admin only."""
    service = CredentialService(db)
    try:
        return await service.get_credentials(credential_id)
    except CredentialNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{credential_id}", response_model=CredentialSetResponse)
async def update_credentials(
    credential_id: UUID,
    data: CredentialSetUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update credentials. Admin only."""
    service = CredentialService(db)
    try:
        cred_set = await service.update_credentials(
            credential_id=credential_id,
            auth_type=data.auth_type,
            payload=data.payload,
            is_active=data.is_active,
        )
        await db.commit()
        return cred_set
    except CredentialNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CredentialError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(
    credential_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete credentials. Admin only."""
    service = CredentialService(db)
    try:
        await service.delete_credentials(credential_id)
        await db.commit()
    except CredentialNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
