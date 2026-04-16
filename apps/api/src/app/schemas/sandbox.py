"""
Sandbox Pydantic schemas.

Pattern: Create, Update, ListItem, DetailResponse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Session ──────────────────────────────────────────────────────────────────

class SandboxSessionCreate(BaseModel):
    name: Optional[str] = None
    ttl_days: int = Field(default=14, ge=1, le=90)


class SandboxSessionUpdate(BaseModel):
    name: Optional[str] = None
    ttl_days: Optional[int] = Field(default=None, ge=1, le=90)


class SandboxSessionListItem(BaseModel):
    id: UUID
    owner_id: UUID
    owner_email: str
    name: str
    status: str
    ttl_days: int
    expires_at: datetime
    last_activity_at: datetime
    overrides_count: int = 0
    runs_count: int = 0
    created_at: datetime


class SandboxSessionDetailResponse(BaseModel):
    id: UUID
    owner_id: UUID
    owner_email: str
    name: str
    status: str
    ttl_days: int
    expires_at: datetime
    last_activity_at: datetime
    overrides: list[SandboxOverrideResponse] = []
    runs: list[SandboxRunListItem] = []
    created_at: datetime
    updated_at: datetime


# ── Branch ───────────────────────────────────────────────────────────────────

class SandboxBranchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_branch_id: Optional[UUID] = None
    parent_run_id: Optional[UUID] = None


class SandboxBranchForkRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_run_id: Optional[UUID] = None
    copy_overrides: bool = True


class SandboxBranchListItem(BaseModel):
    id: UUID
    session_id: UUID
    parent_branch_id: Optional[UUID] = None
    parent_run_id: Optional[UUID] = None
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class SandboxBranchOverrideUpsert(BaseModel):
    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: Optional[UUID] = None
    field_path: str = Field(..., min_length=1, max_length=255)
    value_json: dict[str, Any] | list[Any] | str | int | float | bool | None
    value_type: str = Field(default="json", min_length=1, max_length=50)


class SandboxBranchOverrideResponse(BaseModel):
    id: UUID
    branch_id: UUID
    entity_type: str
    entity_id: Optional[UUID] = None
    field_path: str
    value_json: Any
    value_type: str
    updated_by: UUID
    created_at: datetime
    updated_at: datetime


class SandboxSnapshotResponse(BaseModel):
    id: UUID
    session_id: UUID
    branch_id: UUID
    snapshot_hash: str
    payload_json: dict[str, Any]
    created_by: UUID
    created_at: datetime


# ── Override ─────────────────────────────────────────────────────────────────

class SandboxOverrideCreate(BaseModel):
    entity_type: str = Field(..., pattern=r"^(agent_version|discovered_tool|tool_release|orchestration|policy|limit|model)$")
    entity_id: Optional[UUID] = None
    label: str = Field(..., min_length=1, max_length=255)
    is_active: bool = False
    config_snapshot: dict[str, Any]


class SandboxOverrideUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    config_snapshot: Optional[dict[str, Any]] = None


class SandboxOverrideResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: Optional[UUID] = None
    label: str
    is_active: bool
    config_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Run ──────────────────────────────────────────────────────────────────────

class SandboxRunCreate(BaseModel):
    request_text: str = Field(..., min_length=1)
    branch_id: Optional[UUID] = None
    parent_run_id: Optional[UUID] = None
    attachment_ids: Optional[list[UUID]] = None


class SandboxRunListItem(BaseModel):
    id: UUID
    branch_id: Optional[UUID] = None
    snapshot_id: Optional[UUID] = None
    parent_run_id: Optional[UUID] = None
    request_text: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    steps_count: int = 0


class SandboxRunDetailResponse(BaseModel):
    id: UUID
    branch_id: Optional[UUID] = None
    snapshot_id: Optional[UUID] = None
    parent_run_id: Optional[UUID] = None
    request_text: str
    status: str
    effective_config: dict[str, Any]
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    steps: list[SandboxRunStepResponse] = []


# ── Run Step ─────────────────────────────────────────────────────────────────

class SandboxRunStepResponse(BaseModel):
    id: UUID
    step_type: str
    step_data: dict[str, Any]
    order_num: int
    created_at: datetime


# ── Actions ──────────────────────────────────────────────────────────────────

class SandboxConfirmAction(BaseModel):
    confirmed: bool


# ── Catalog ─────────────────────────────────────────────────────────────────

class SandboxCatalogToolVersion(BaseModel):
    id: UUID
    version: int
    status: str


class SandboxCatalogToolItem(BaseModel):
    id: UUID
    tool_id: Optional[UUID] = None
    slug: str
    name: str
    description: Optional[str] = None
    source: str = "local"
    domains: list[str] = []
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    published: bool = False
    current_version_id: Optional[UUID] = None
    versions: list[SandboxCatalogToolVersion] = []


class SandboxCatalogDomainGroup(BaseModel):
    domain: str
    tools: list[SandboxCatalogToolItem] = []


class SandboxResolverFieldSpec(BaseModel):
    key: str
    label: str
    field_path: str
    field_type: str = "text"
    editable: bool = True
    options: list[str] = []
    help_text: Optional[str] = None
    source_key: Optional[str] = None


class SandboxResolverSectionSpec(BaseModel):
    title: str
    fields: list[SandboxResolverFieldSpec] = []


class SandboxResolverBlueprint(BaseModel):
    key: str
    title: str
    entity_type: str
    entity_id: Optional[str] = None
    description: Optional[str] = None
    sections: list[SandboxResolverSectionSpec] = []


class SandboxCatalogAgentVersion(BaseModel):
    id: UUID
    version: int
    status: str


class SandboxCatalogAgentItem(BaseModel):
    id: UUID
    slug: str
    name: str
    current_version_id: Optional[UUID] = None
    versions: list[SandboxCatalogAgentVersion] = []


class SandboxCatalogRouterItem(BaseModel):
    id: str
    name: str
    description: str


class SandboxCatalogResponse(BaseModel):
    tools: list[SandboxCatalogToolItem] = []
    domain_groups: list[SandboxCatalogDomainGroup] = []
    agents: list[SandboxCatalogAgentItem] = []
    system_routers: list[SandboxCatalogRouterItem] = []
    resolver_blueprints: list[SandboxResolverBlueprint] = []


# Fix forward refs
SandboxSessionDetailResponse.model_rebuild()
