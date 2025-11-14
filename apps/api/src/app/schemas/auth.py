"""
Authentication schemas for API v1
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AuthLoginRequest(BaseModel):
    """Request schema for /auth/login"""
    email: str = Field(..., description="User email address", min_length=1, max_length=255)
    password: str = Field(..., description="User password", min_length=1)


class AuthRefreshRequest(BaseModel):
    """Request schema for /auth/refresh"""
    refresh_token: str = Field(..., description="Refresh token", min_length=1)


class UserMeResponse(BaseModel):
    """Response schema for /auth/me - filtered user data"""
    id: str = Field(..., description="User ID")
    role: str = Field(..., description="User role")
    login: Optional[str] = Field(None, description="User login/email")
    fio: Optional[str] = Field(None, description="User full name")


class AuthTokensResponse(BaseModel):
    """Response schema for /auth/login and /auth/refresh"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    refresh_expires_in: Optional[int] = Field(None, description="Refresh token expiration in seconds")
    user: Optional[UserMeResponse] = Field(None, description="User information")


class PasswordForgotRequest(BaseModel):
    """Request schema for /auth/password/forgot"""
    email: str = Field(..., description="User email address", min_length=1, max_length=255)


class PasswordResetRequest(BaseModel):
    """Request schema for /auth/password/reset"""
    token: str = Field(..., description="Password reset token", min_length=1)
    new_password: str = Field(..., description="New password", min_length=8)


class PasswordResetResponse(BaseModel):
    """Response schema for /auth/password/reset"""
    message: str = Field(..., description="Success message")


class PATTokenCreateRequest(BaseModel):
    """Request schema for creating PAT token"""
    name: str = Field(..., description="Token name", min_length=1, max_length=100)
    expires_at: int = Field(..., description="Token expiration timestamp")


class PATTokenResponse(BaseModel):
    """Response schema for PAT token"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    token: Optional[str] = Field(None, description="Token value (only on creation)")
    token_mask: str = Field(..., description="Masked token for display")
    created_at: str = Field(..., description="Creation timestamp")
    expires_at: int = Field(..., description="Expiration timestamp")
    last_used_at: Optional[str] = Field(None, description="Last usage timestamp")
    is_active: bool = Field(..., description="Token active status")


class PATTokensListResponse(BaseModel):
    """Response schema for PAT tokens list"""
    tokens: list[PATTokenResponse] = Field(..., description="List of PAT tokens")