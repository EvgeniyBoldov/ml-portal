"""Admin API contracts for user management."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.memory_scope_preferences import MemoryScopeKeys


class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    READER = "reader"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    login: str = Field(min_length=3, max_length=255)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8)
    role: UserRole = UserRole.READER
    is_admin: bool = False
    is_active: bool = True
    tenant_id: Optional[UUID] = None
    memory_scope_keys: MemoryScopeKeys = Field(default_factory=list)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[UUID] = None
    memory_scope_keys: Optional[MemoryScopeKeys] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    login: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: UserRole
    is_admin: bool = False
    is_active: bool
    auth_provider: str = "local"
    deactivated_reason: Optional[str] = None
    tenant_id: Optional[UUID] = None
    memory_scope_keys: MemoryScopeKeys = Field(default_factory=list)
    lifecycle_status: str = "active"
    deprecated_at: Optional[datetime] = None
    retention_days: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UserListResponse(BaseModel):
    users: list[UserResponse]
    has_more: bool
    next_cursor: Optional[str] = None
    total: int


class UserPasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=8)
