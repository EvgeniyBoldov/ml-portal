"""
Pydantic schemas for RBAC rules API.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RbacRuleCreate(BaseModel):
    level: str = Field(..., description="platform | tenant | user")
    resource_type: str = Field(..., description="agent | tool | instance")
    resource_id: UUID
    effect: str = Field(..., description="allow | deny")
    owner_user_id: Optional[UUID] = Field(None, description="User owner (for user-level rules)")
    owner_tenant_id: Optional[UUID] = Field(None, description="Tenant owner (for tenant-level rules)")
    owner_platform: bool = Field(False, description="Platform owner (for platform-level rules)")


class RbacRuleUpdate(BaseModel):
    effect: str = Field(..., description="allow | deny")


class RbacRuleResponse(BaseModel):
    id: UUID
    level: str
    owner_user_id: Optional[UUID]
    owner_tenant_id: Optional[UUID]
    owner_platform: bool
    resource_type: str
    resource_id: UUID
    effect: str
    created_at: datetime
    created_by_user_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


class CheckAccessRequest(BaseModel):
    user_id: UUID
    tenant_id: UUID
    resource_type: str
    resource_id: UUID


class CheckAccessResponse(BaseModel):
    effect: str
    resource_type: str
    resource_id: UUID


# ─── Enriched Rules Response ─────────────────────────────────────────

class EnrichedOwnerInfo(BaseModel):
    level: str
    name: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    platform: bool = False

class EnrichedResourceInfo(BaseModel):
    type: str
    id: str
    name: str
    slug: Optional[str] = None

class EnrichedRuleResponse(BaseModel):
    id: str
    owner: EnrichedOwnerInfo
    resource: EnrichedResourceInfo
    effect: str
    created_at: str
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None
