"""
API Keys management endpoints.

Allows users to create, list, and revoke API keys for IDE plugins.
"""
from __future__ import annotations
from app.core.logging import get_logger
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, require_admin
from app.core.security import UserCtx
from app.services.api_key_service import APIKeyService

logger = get_logger(__name__)

router = APIRouter()


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    allowed_tools: Optional[List[str]] = None
    allowed_prompts: Optional[List[str]] = None
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    key_prefix: str
    scopes: List[str]
    allowed_tools: Optional[List[str]]
    allowed_prompts: Optional[List[str]]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreatedResponse(APIKeyResponse):
    """Response with the raw key (only shown once!)."""
    raw_key: str


@router.post("", response_model=APIKeyCreatedResponse)
async def create_api_key(
    data: APIKeyCreate,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    """
    Create a new API key.
    
    **Important**: The raw key is only shown once! Save it securely.
    """
    service = APIKeyService(session)
    
    tenant_id = current_user.tenant_ids[0] if current_user.tenant_ids else None
    
    api_key, raw_key = await service.create_key(
        name=data.name,
        user_id=current_user.id,
        tenant_id=tenant_id,
        description=data.description,
        scopes=data.scopes,
        allowed_tools=data.allowed_tools,
        allowed_prompts=data.allowed_prompts,
        expires_at=data.expires_at,
    )
    
    await session.commit()
    
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        description=api_key.description,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        allowed_tools=api_key.allowed_tools,
        allowed_prompts=api_key.allowed_prompts,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        raw_key=raw_key,
    )


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    """List all API keys for the current user."""
    service = APIKeyService(session)
    keys = await service.list_keys(user_id=current_user.id)
    return keys


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    """Revoke (deactivate) an API key."""
    service = APIKeyService(session)
    
    api_key = await service.get_key_by_id(key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    
    if api_key.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await service.revoke_key(key_id)
    await session.commit()
    
    return {"status": "revoked"}
