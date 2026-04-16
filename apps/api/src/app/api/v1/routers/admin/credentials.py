"""
Credentials Admin API v2 (owner-based)
"""
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.credential_service import CredentialService
from app.schemas.tool_instances import (
    CredentialCreate,
    CredentialUpdate,
    CredentialResponse,
)

router = APIRouter(tags=["credentials"])


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return "*" * len(value)


def _build_masked_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    masked: Dict[str, str] = {}
    for key, raw_value in payload.items():
        if raw_value is None:
            masked[key] = ""
            continue
        value = str(raw_value)
        masked[key] = _mask_secret(value)
    return masked


async def _to_credential_response(service: CredentialService, credential_id: UUID) -> CredentialResponse:
    cred = await service.get_credentials(credential_id)
    decrypted = await service.get_decrypted_credentials(credential_id)
    has_payload = bool(cred.encrypted_payload and str(cred.encrypted_payload).strip())
    return CredentialResponse(
        id=cred.id,
        instance_id=cred.instance_id,
        owner_user_id=cred.owner_user_id,
        owner_tenant_id=cred.owner_tenant_id,
        owner_platform=cred.owner_platform,
        auth_type=cred.auth_type,
        is_active=cred.is_active,
        has_payload=has_payload,
        masked_payload=_build_masked_payload(decrypted.payload),
        created_at=cred.created_at,
    )


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
    response: List[CredentialResponse] = []
    for cred in creds:
        response.append(await _to_credential_response(service, cred.id))
    return response


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credentials(
    data: CredentialCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new credential. Exactly one owner must be set."""
    service = CredentialService(db)
    cred = await service.create_credentials(
        instance_id=data.instance_id,
        auth_type=data.auth_type,
        payload=data.payload,
        owner_user_id=data.owner_user_id,
        owner_tenant_id=data.owner_tenant_id,
        owner_platform=data.owner_platform,
    )
    await db.commit()
    return await _to_credential_response(service, cred.id)


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credentials(
    credential_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get credential by ID. Admin only."""
    service = CredentialService(db)
    return await _to_credential_response(service, credential_id)


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credentials(
    credential_id: UUID,
    data: CredentialUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update credential. Admin only."""
    service = CredentialService(db)
    cred = await service.update_credentials(
        credential_id=credential_id,
        auth_type=data.auth_type,
        payload=data.payload,
        is_active=data.is_active,
    )
    await db.commit()
    return await _to_credential_response(service, cred.id)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(
    credential_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete credential. Admin only."""
    service = CredentialService(db)
    await service.delete_credentials(credential_id)
    await db.commit()
