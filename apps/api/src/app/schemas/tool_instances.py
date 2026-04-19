"""
Pydantic schemas for ToolInstance API (v3).

Instance v3 classification axes:
- connector_type: data | mcp | model
- connector_subtype: sql | api (for data connectors)
- placement: local | remote

Credentials and RoutingLogs schemas live in their own files:
- app.schemas.credentials
- app.schemas.routing_logs
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator, ConfigDict

# Re-exports for backward compatibility
from app.schemas.credentials import CredentialCreate, CredentialUpdate, CredentialResponse  # noqa: F401
from app.schemas.routing_logs import RoutingLogResponse  # noqa: F401


# ── ToolInstance ─────────────────────────────────────────────────────

class ToolInstanceCreate(BaseModel):
    slug: Optional[str] = Field(
        None,
        max_length=255,
        pattern="^[a-z][a-z0-9_-]{1,254}$",
        description="Auto-generated from name if not provided",
    )
    name: str
    description: Optional[str] = None
    instance_kind: str = Field("data", pattern="^(data|service)$", description="data | service")
    connector_type: str = Field(
        "data",
        pattern="^(data|mcp|model)$",
        description="Connector type: data | mcp | model",
    )
    connector_subtype: Optional[str] = Field(
        default=None,
        pattern="^(sql|api)$",
        description="Data connector subtype: sql | api",
    )
    url: str = ""
    provider_kind: Optional[str] = Field(
        default=None,
        description="Explicit provider capability flag (e.g. mcp, local_tables, local_documents, local_runtime)",
    )
    config: Optional[Dict[str, Any]] = None
    access_via_instance_id: Optional[UUID] = Field(None, description="Service instance for accessing this data instance")

    @model_validator(mode="after")
    def validate_subtype(self) -> "ToolInstanceCreate":
        if self.connector_type == "data" and not self.connector_subtype:
            raise ValueError("connector_subtype is required for data connectors")
        if self.connector_type != "data" and self.connector_subtype is not None:
            raise ValueError("connector_subtype is allowed only for data connectors")
        return self


class ToolInstanceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instance_kind: Optional[str] = Field(default=None, pattern="^(data|service)$")
    connector_type: Optional[str] = Field(default=None, pattern="^(data|mcp|model)$")
    connector_subtype: Optional[str] = Field(default=None, pattern="^(sql|api)$")
    url: Optional[str] = None
    provider_kind: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    access_via_instance_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_subtype(self) -> "ToolInstanceUpdate":
        if self.connector_type is not None and self.connector_type != "data" and self.connector_subtype is not None:
            raise ValueError("connector_subtype is allowed only for data connectors")
        return self


class ToolInstanceListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    instance_kind: str
    connector_type: str
    connector_subtype: Optional[str] = None
    placement: str
    provider_kind: Optional[str] = None
    url: str
    health_status: Optional[str] = None
    is_active: bool
    access_via_instance_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ToolInstanceResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    instance_kind: str
    connector_type: str
    connector_subtype: Optional[str] = None
    placement: str
    provider_kind: Optional[str] = None
    url: str
    config: Optional[Dict[str, Any]] = None
    health_status: Optional[str] = None
    is_active: bool
    access_via_instance_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RuntimeOperationListItem(BaseModel):
    operation_slug: str
    operation: str
    source: str
    discovered_tool_slug: str
    provider_instance_slug: Optional[str] = None
    risk_level: str
    side_effects: str
    idempotent: bool
    requires_confirmation: bool


class ToolInstanceDetailResponse(ToolInstanceResponse):
    access_via_name: Optional[str] = None
    runtime_operations: List[RuntimeOperationListItem] = Field(default_factory=list)


# ── Utility ──────────────────────────────────────────────────────────

class HealthCheckResponse(BaseModel):
    status: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class RescanResponse(BaseModel):
    created: int
    updated: int
    deleted: int
    errors: int


class LinkedDataInstanceRuntimeSummary(BaseModel):
    instance_id: UUID
    slug: str
    connector_subtype: Optional[str] = None
    is_runtime_ready: bool
    runtime_readiness_reason: str
    semantic_source: str
    discovered_tools_count: int
    runtime_operations_count: int


class InstanceRuntimeOnboardRequest(BaseModel):
    enable_all_in_runtime: bool = False
    include_local_tools: bool = False
    include_inactive_linked: bool = False


class InstanceRuntimeOnboardResponse(BaseModel):
    provider_instance_id: UUID
    provider_slug: str
    onboarding: Dict[str, Any]
    linked_instances_total: int
    linked_ready_count: int
    linked_not_ready_count: int
    linked_runtime_operations_total: int
    linked_instances: List[LinkedDataInstanceRuntimeSummary] = Field(default_factory=list)
