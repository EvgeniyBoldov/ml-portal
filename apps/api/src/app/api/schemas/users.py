"""
User-related API schemas
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, EmailStr
from enum import Enum

class UserRole(str, Enum):
    """User roles"""
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"

class UserStatus(str, Enum):
    """User status"""
    ACTIVE = "active"
    INACTIVE = "inactive"

class AuditAction(str, Enum):
    """Audit action types"""
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"
    PASSWORD_RESET = "password_reset"
    TOKEN_CREATED = "token_created"
    TOKEN_REVOKED = "token_revoked"

# Request schemas
class UserCreateRequest(BaseModel):
    """User creation request"""
    login: str = Field(..., min_length=3, max_length=100, description="User login")
    password: str = Field(..., min_length=8, max_length=255, description="User password")
    email: Optional[EmailStr] = Field(None, description="User email")
    role: UserRole = Field(UserRole.READER, description="User role")
    is_active: bool = Field(True, description="User active status")
    
    @field_validator('login')
    @classmethod
    def validate_login(cls, v):
        if not v or not v.strip():
            raise ValueError('Login cannot be empty')
        return v.strip().lower()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserUpdateRequest(BaseModel):
    """User update request"""
    email: Optional[EmailStr] = Field(None, description="User email")
    role: Optional[UserRole] = Field(None, description="User role")
    is_active: Optional[bool] = Field(None, description="User active status")

class UserSearchRequest(BaseModel):
    """User search request"""
    query: Optional[str] = Field(None, min_length=2, max_length=100, description="Search query")
    role: Optional[UserRole] = Field(None, description="Filter by role")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class PasswordChangeRequest(BaseModel):
    """Password change request"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=255, description="New password")
    
    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr = Field(..., description="User email")

class PasswordResetConfirmRequest(BaseModel):
    """Password reset confirmation request"""
    token: str = Field(..., description="Reset token")
    new_password: str = Field(..., min_length=8, max_length=255, description="New password")
    
    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

# Alias for backward compatibility
PasswordResetConfirm = PasswordResetConfirmRequest

class AuditLogResponse(BaseModel):
    """Audit log response"""
    id: str = Field(..., description="Audit log ID")
    actor_user_id: Optional[str] = Field(None, description="Actor user ID")
    action: str = Field(..., description="Action performed")
    object_type: Optional[str] = Field(None, description="Object type")
    object_id: Optional[str] = Field(None, description="Object ID")
    meta: Optional[Dict[str, Any]] = Field(None, description="Action details")
    ip: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    request_id: Optional[str] = Field(None, description="Request ID")
    ts: datetime = Field(..., description="Creation timestamp")
    
    model_config = {"from_attributes": True}
    
    @field_validator('id', 'actor_user_id', mode='before')
    @classmethod
    def convert_id_to_str(cls, v):
        """Convert UUID to string"""
        return str(v) if v is not None else None

class AuditLogListResponse(BaseModel):
    """Audit log list response"""
    logs: List[AuditLogResponse] = Field(..., description="List of audit logs")
    total: int = Field(..., description="Total count")
    has_more: bool = Field(..., description="Has more results")
    next_cursor: Optional[str] = Field(None, description="Next cursor for pagination")

class PATTokenCreateRequest(BaseModel):
    """PAT token creation request"""
    name: str = Field(..., min_length=1, max_length=100, description="Token name")
    scopes: Optional[List[str]] = Field(None, description="Token scopes")
    expires_at: Optional[datetime] = Field(None, description="Token expiration")
    
    @field_validator('scopes')
    @classmethod
    def validate_scopes(cls, v):
        if v is None:
            return None
        valid_scopes = [
            'api:admin', 'api:read', 'api:write',
            'chat:admin', 'chat:read', 'chat:write', 
            'rag:admin', 'rag:read', 'rag:write',
            'users:admin', 'users:read', 'users:write'
        ]
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f'Invalid scope: {scope}. Valid scopes: {valid_scopes}')
        return v

# Alias for backward compatibility
TokenCreateRequest = PATTokenCreateRequest

class TokenResponse(BaseModel):
    """Token response"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    scopes: List[str] = Field(..., description="Token scopes")
    expires_at: Optional[datetime] = Field(None, description="Token expiration")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last used timestamp")
    token_plain_once: Optional[str] = Field(None, description="Plain token (only on creation)")
    
    model_config = {"from_attributes": True}
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_id_to_str(cls, v):
        """Convert UUID to string"""
        return str(v) if v is not None else None

class TokenListResponse(BaseModel):
    """Token list response"""
    tokens: List[TokenResponse] = Field(..., description="List of tokens")
    total: int = Field(..., description="Total count")

class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    request_id: Optional[str] = Field(None, description="Request ID")
    details: Optional[Dict[str, Any]] = Field(None, description="Error details")

# Response schemas
class UserResponse(BaseModel):
    """User response"""
    id: str = Field(..., description="User ID")
    login: str = Field(..., description="User login")
    email: Optional[str] = Field(None, description="User email")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="User active status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    """User list response"""
    users: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(..., description="Offset applied")
    has_more: bool = Field(..., description="Whether there are more results")

class UserStatsResponse(BaseModel):
    """User statistics response"""
    user_id: str = Field(..., description="User ID")
    login: str = Field(..., description="User login")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="User active status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    active_tokens: int = Field(..., description="Number of active tokens")
    total_tokens: int = Field(..., description="Total number of tokens")

class PATTokenResponse(BaseModel):
    """PAT token response"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    scopes: Optional[List[str]] = Field(None, description="Token scopes")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    revoked_at: Optional[datetime] = Field(None, description="Revocation timestamp")
    is_active: bool = Field(..., description="Whether token is active")
    
    class Config:
        from_attributes = True

class PATTokenCreateResponse(BaseModel):
    """PAT token creation response"""
    token: PATTokenResponse = Field(..., description="Token information")
    access_token: str = Field(..., description="Access token (only shown once)")

class PATTokenListResponse(BaseModel):
    """PAT token list response"""
    tokens: List[PATTokenResponse] = Field(..., description="List of tokens")
    total: int = Field(..., description="Total number of tokens")

# Authentication schemas
class LoginRequest(BaseModel):
    """Login request"""
    login: str = Field(..., min_length=3, max_length=100, description="User login")
    password: str = Field(..., min_length=1, description="User password")
    
    @field_validator('login')
    @classmethod
    def validate_login(cls, v):
        if not v or not v.strip():
            raise ValueError('Login cannot be empty')
        return v.strip().lower()

class LoginResponse(BaseModel):
    """Login response"""
    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(3600, description="Token expiration in seconds")
    user: UserResponse = Field(..., description="User information")

class RefreshRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")

class RefreshResponse(BaseModel):
    """Refresh token response"""
    access_token: str = Field(..., description="New access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(3600, description="Token expiration in seconds")
