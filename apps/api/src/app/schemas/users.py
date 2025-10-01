"""
User schemas
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    EDITOR = "editor"
    READER = "reader"


class AuditAction(str, Enum):
    """Audit action types"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_RESET = "password_reset"


class UserBase(BaseModel):
    """Base user schema"""
    model_config = ConfigDict(from_attributes=True)
    
    email: str
    role: UserRole = UserRole.READER
    is_active: bool = True


class UserCreate(UserBase):
    """User creation schema"""
    password: str


class UserUpdate(BaseModel):
    """User update schema"""
    model_config = ConfigDict(from_attributes=True)
    
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response schema"""
    id: uuid.UUID
    created_at: str
    updated_at: Optional[str] = None
