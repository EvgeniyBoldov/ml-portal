# Tenant schemas and models

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tenant name")
    description: Optional[str] = Field(None, max_length=500, description="Tenant description")
    is_active: bool = Field(True, description="Whether tenant is active")

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None

class Tenant(TenantBase):
    id: str = Field(..., description="Tenant ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True

class TenantListResponse(BaseModel):
    tenants: list[Tenant]
    total: int
    page: int
    size: int
    has_more: bool
