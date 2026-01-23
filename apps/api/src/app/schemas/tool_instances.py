"""
Pydantic schemas for ToolInstance API
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class ToolInstanceCreate(BaseModel):
    """Schema for creating a tool instance"""
    tool_slug: str = Field(..., description="Slug of the tool")
    slug: str = Field(..., description="Unique slug for this instance")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    scope: str = Field(..., description="Scope: default, tenant, user")
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    connection_config: Dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class ToolInstanceUpdate(BaseModel):
    """Schema for updating a tool instance"""
    name: Optional[str] = None
    description: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class ToolInstanceResponse(BaseModel):
    """Schema for tool instance response"""
    id: UUID
    tool_id: UUID
    slug: str
    name: str
    description: Optional[str]
    scope: str
    tenant_id: Optional[UUID]
    user_id: Optional[UUID]
    connection_config: Dict[str, Any]
    is_default: bool
    is_active: bool
    health_status: str
    last_health_check_at: Optional[datetime]
    health_check_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthCheckResponse(BaseModel):
    """Schema for health check response"""
    status: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class CredentialSetCreate(BaseModel):
    """Schema for creating credentials"""
    tool_instance_id: UUID
    auth_type: str = Field(..., description="Auth type: token, basic, oauth, api_key")
    payload: Dict[str, Any] = Field(..., description="Credentials payload")
    scope: str = Field(..., description="Scope: tenant, user")
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None


class CredentialSetUpdate(BaseModel):
    """Schema for updating credentials"""
    auth_type: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class CredentialSetResponse(BaseModel):
    """Schema for credential set response (without decrypted payload)"""
    id: UUID
    tool_instance_id: UUID
    scope: str
    tenant_id: Optional[UUID]
    user_id: Optional[UUID]
    auth_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PermissionSetCreate(BaseModel):
    """Schema for creating permission set"""
    scope: str = Field(..., description="Scope: default, tenant, user")
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    allowed_tools: List[str] = Field(default_factory=list)
    denied_tools: List[str] = Field(default_factory=list)
    allowed_collections: List[str] = Field(default_factory=list)
    denied_collections: List[str] = Field(default_factory=list)


class PermissionSetUpdate(BaseModel):
    """Schema for updating permission set"""
    allowed_tools: Optional[List[str]] = None
    denied_tools: Optional[List[str]] = None
    allowed_collections: Optional[List[str]] = None
    denied_collections: Optional[List[str]] = None


class PermissionSetResponse(BaseModel):
    """Schema for permission set response"""
    id: UUID
    scope: str
    tenant_id: Optional[UUID]
    user_id: Optional[UUID]
    allowed_tools: List[str]
    denied_tools: List[str]
    allowed_collections: List[str]
    denied_collections: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EffectivePermissionsResponse(BaseModel):
    """Schema for resolved effective permissions"""
    allowed_tools: List[str]
    denied_tools: List[str]
    allowed_collections: List[str]
    denied_collections: List[str]


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
