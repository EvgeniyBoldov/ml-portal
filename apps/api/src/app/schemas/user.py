"""
User schemas with RBAC permissions
"""
from typing import Optional, List
from uuid importUUID
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from app.models.user import Users
from app.models.rag import DocumentScope


class UserRole(str, Enum):
    """Available user roles"""
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"


class UserRoleUpdate(BaseModel):
    """Schema for updating user role"""
    role: UserRole = Field(..., description="New user role")


class UserPermissionFlagsUpdate(BaseModel):
    """Schema for updating user permission flags"""
    can_edit_local_docs: Optional[bool] = Field(None, description="Can edit local documents")
    can_edit_global_docs: Optional[bool] = Field(None, description="Can edit global documents")
    can_trigger_reindex: Optional[bool] = Field(None, description="Can trigger reindexing")
    can_manage_users: Optional[bool] = Field(None, description="Can manage users and roles")


class UserTenantsUpdate(BaseModel):
    """Schema for updating user tenant associations"""
    tenant_ids: List[UUID] = Field(..., description="List of tenant IDs user belongs to")
    default_tenant_id: Optional[UUID] = Field(None, description="Default tenant for user")


class UserResponse(BaseModel):
    """User response schema"""
    id: str = Field(..., description="User ID")
    login: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    is_active: bool = Field(..., description="Is user active")
    role: str = Field(..., description="User role")
    
    # Permission flags
    can_edit_local_docs: bool = Field(..., description="Can edit local documents")
    can_edit_global_docs: bool = Field(..., description="Can edit global documents")
    can_trigger_reindex: bool = Field(..., description="Can trigger reindexing")
    can_manage_users: bool = Field(..., description="Can manage users and roles")
    
    # Timestamps
    created_at: datetime = Field(..., description="User creation time")
    updated_at: datetime = Field(..., description="User last update time")
    
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Schema for creating users"""
    login: str = Field(..., min_length=3, max_length=50, description="Username")
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=10, description="Password")
    role: UserRole = Field(default=UserRole.READER, description="User role")
    
    # Permission flags
    can_edit_local_docs: bool = Field(default=False, description="Can edit local documents")
    can_edit_global_docs: bool = Field(default=False, description="Can edit global documents")
    can_trigger_reindex: bool = Field(default=False, description="Can trigger reindexing")
    can_manage_users: bool = Field(default=False, description="Can manage users and roles")
    
    # Tenant associations
    tenant_ids: List[UUID] = Field(default=[], description="Tenants user belongs to")
    default_tenant_id: Optional[UUID] = Field(None, description="Default tenant")


class UserUpdate(BaseModel):
    """Schema for updating users"""
    login: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=10)
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None
    
    # Permission flags
    can_edit_local_docs: Optional[bool] = None
    can_edit_global_docs: Optional[bool] = None
    can_trigger_reindex: Optional[bool] = None
    can_manage_users: Optional[bool] = None
    
    class Config:
        validate_assignment = True
