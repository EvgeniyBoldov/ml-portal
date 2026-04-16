"""
Pydantic schemas for Credentials API (v2 owner-based).
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class CredentialCreate(BaseModel):
    instance_id: UUID
    auth_type: str = Field(..., description="token | basic | oauth | api_key")
    payload: Dict[str, Any] = Field(..., description="Credentials payload (will be encrypted)")
    owner_user_id: Optional[UUID] = None
    owner_tenant_id: Optional[UUID] = None
    owner_platform: bool = False


class CredentialUpdate(BaseModel):
    auth_type: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class CredentialResponse(BaseModel):
    id: UUID
    instance_id: UUID
    owner_user_id: Optional[UUID] = None
    owner_tenant_id: Optional[UUID] = None
    owner_platform: bool
    auth_type: str
    is_active: bool
    has_payload: bool = False
    masked_payload: Optional[Dict[str, str]] = None
    created_at: datetime

    class Config:
        from_attributes = True
