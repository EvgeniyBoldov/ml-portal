"""
Credentials Admin API v2 (owner-based)
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
)
from app.schemas.tool_instances import (
    CredentialCreate,
    CredentialUpdate,
    CredentialResponse,
)

router = APIRouter(tags=["credentials"])


@router.get("", response_model=List[CredentialResponse])
async def list_credentials(
    skip: int = 0,
    limit: int = 100,
    instance_id: Optional[UUID] = Query(None, description="Filter by tool instance"),
    owner_user_id: Optional[UUID] = Query(None, description="Filter by owner user"),
    owner_tenant_id: Optional[UUID] = Query(None, description="Filter by owner tenant"),
    owner_platform: Optional[bool] = Query(None, description="Filter platform creds"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all credentials. Admin only."""
    service = CredentialService(db)
    creds, _ = await service.list_credentials(
        skip=skip,
        limit=limit,
        instance_id=instance_id,
        owner_user_id=owner_user_id,
        owner_tenant_id=owner_tenant_id,
        owner_platform=owner_platform,
        is_active=is_active,
    )
    return creds


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credentials(
    data: CredentialCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new credential. Exactly one owner must be set."""
    service = CredentialService(db)
    try:
        cred = await service.create_credentials(
            instance_id=data.instance_id,
            auth_type=data.auth_type,
            payload=data.payload,
            owner_user_id=data.owner_user_id,
            owner_tenant_id=data.owner_tenant_id,
            owner_platform=data.owner_platform,
        )
        await db.commit()
        return cred
    except CredentialError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credentials(
    credential_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get credential by ID. Admin only."""
    service = CredentialService(db)
    try:
        return await service.get_credentials(credential_id)
    except CredentialNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credentials(
    credential_id: UUID,
    data: CredentialUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update credential. Admin only."""
    service = CredentialService(db)
    try:
        cred = await service.update_credentials(
            credential_id=credential_id,
            auth_type=data.auth_type,
            payload=data.payload,
            is_active=data.is_active,
        )
        await db.commit()
        return cred
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
    """Delete credential. Admin only."""
    service = CredentialService(db)
    try:
        await service.delete_credentials(credential_id)
        await db.commit()
    except CredentialNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
