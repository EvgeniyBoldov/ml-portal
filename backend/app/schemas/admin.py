from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    READER = "reader"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


# User schemas
class UserBase(BaseModel):
    login: str = Field(..., min_length=3, max_length=255)
    role: UserRole = Field(default=UserRole.READER)
    email: Optional[str] = Field(None, max_length=255)
    is_active: bool = Field(default=True)


class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=12)
    
    @validator('password')
    def validate_password(cls, v):
        if v is not None:
            # Basic password policy validation
            if len(v) < 12:
                raise ValueError('Password must be at least 12 characters long')
            # Add more complex validation if needed
        return v


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    email: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    require_password_change: Optional[bool] = None


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    has_more: bool
    next_cursor: Optional[str] = None


# Password reset schemas
class PasswordResetRequest(BaseModel):
    login_or_email: str = Field(..., min_length=1)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12)


class PasswordChange(BaseModel):
    new_password: Optional[str] = Field(None, min_length=12)
    
    @validator('new_password')
    def validate_password(cls, v):
        if v is not None and len(v) < 12:
            raise ValueError('Password must be at least 12 characters long')
        return v


# PAT Token schemas
class TokenScope(str, Enum):
    API_READ = "api:read"
    API_WRITE = "api:write"
    RAG_ALL = "rag:*"
    RAG_READ = "rag:read"
    RAG_WRITE = "rag:write"
    CHAT_ALL = "chat:*"
    CHAT_READ = "chat:read"
    CHAT_WRITE = "chat:write"


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: Optional[List[TokenScope]] = Field(default=None)
    expires_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    id: str
    name: str
    scopes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    token_plain_once: Optional[str] = None  # Only returned on creation
    
    class Config:
        from_attributes = True


class TokenListResponse(BaseModel):
    tokens: List[TokenResponse]
    total: int


# Audit log schemas
class AuditAction(str, Enum):
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ACTIVATED = "user_activated"
    USER_DEACTIVATED = "user_deactivated"
    PASSWORD_RESET = "password_reset"
    TOKEN_CREATED = "token_created"
    TOKEN_REVOKED = "token_revoked"
    LOGIN = "login"
    LOGOUT = "logout"
    SYSTEM = "system"


class AuditLogResponse(BaseModel):
    id: str
    ts: datetime
    actor_user_id: Optional[str] = None
    action: str
    object_type: Optional[str] = None
    object_id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    has_more: bool
    next_cursor: Optional[str] = None


# Error response schema
class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
