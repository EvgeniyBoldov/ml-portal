"""
Pydantic schemas for ToolInstance & Credential API (v2)
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


# ── ToolInstance ─────────────────────────────────────────────────────

class ToolInstanceCreate(BaseModel):
    tool_group_id: UUID
    name: str
    url: str = ""
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class ToolInstanceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ToolInstanceResponse(BaseModel):
    id: UUID
    tool_group_id: UUID
    name: str
    description: Optional[str] = None
    url: str
    config: Optional[Dict[str, Any]] = None
    health_status: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ToolInstanceDetailResponse(ToolInstanceResponse):
    tool_group_slug: Optional[str] = None
    tool_group_name: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ── Credential (v2 owner-based) ─────────────────────────────────────

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
    created_at: datetime

    class Config:
        from_attributes = True


class PermissionSetCreate(BaseModel):
    """Schema for creating permission set"""
    scope: str = Field(..., description="Scope: default, tenant, user")
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    instance_permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of instance_slug -> 'allowed'|'denied'|'undefined'"
    )
    agent_permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent_slug -> 'allowed'|'denied'|'undefined'"
    )


class PermissionSetUpdate(BaseModel):
    """Schema for updating permission set"""
    instance_permissions: Optional[Dict[str, str]] = Field(
        None,
        description="Map of instance_slug -> 'allowed'|'denied'|'undefined'"
    )
    agent_permissions: Optional[Dict[str, str]] = Field(
        None,
        description="Map of agent_slug -> 'allowed'|'denied'|'undefined'"
    )


class PermissionSetResponse(BaseModel):
    """Schema for permission set response"""
    id: UUID
    scope: str
    tenant_id: Optional[UUID]
    user_id: Optional[UUID]
    instance_permissions: Dict[str, str]
    agent_permissions: Dict[str, str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EffectivePermissionsResponse(BaseModel):
    """Schema for resolved effective permissions"""
    instance_permissions: Dict[str, bool] = Field(
        ...,
        description="Map of instance_slug -> is_allowed (True/False)"
    )
    agent_permissions: Dict[str, bool] = Field(
        ...,
        description="Map of agent_slug -> is_allowed (True/False)"
    )
    allowed_instances: List[str]
    denied_instances: List[str]
    allowed_agents: List[str]
    denied_agents: List[str]


class RoutingLogResponse(BaseModel):
    """Schema for routing log response"""
    id: UUID
    run_id: UUID
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    request_text: Optional[str]
    intent: Optional[str]
    intent_confidence: Optional[float]
    selected_agent_slug: Optional[str]
    agent_confidence: Optional[float]
    routing_reasons: List[str]
    missing_tools: List[str]
    missing_collections: List[str]
    missing_credentials: List[str]
    execution_mode: Optional[str]
    effective_tools: List[str]
    effective_collections: List[str]
    tool_instances_map: Dict[str, Any]
    routed_at: datetime
    routing_duration_ms: Optional[int]
    status: str
    error_message: Optional[str]

    class Config:
        from_attributes = True
