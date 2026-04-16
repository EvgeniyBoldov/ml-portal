"""
Schemas for DiscoveredTool admin API.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DiscoveredToolListItem(BaseModel):
    id: UUID
    tool_id: Optional[UUID] = None
    slug: str
    name: str
    description: Optional[str] = None
    source: str
    provider_instance_id: Optional[UUID] = None
    connector_slug: Optional[str] = None
    connector_name: Optional[str] = None
    domains: List[str] = Field(default_factory=list)
    is_active: bool = True
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoveredToolDetailResponse(BaseModel):
    id: UUID
    tool_id: Optional[UUID] = None
    slug: str
    name: str
    description: Optional[str] = None
    source: str
    provider_instance_id: Optional[UUID] = None
    connector_slug: Optional[str] = None
    connector_name: Optional[str] = None
    domains: List[str] = Field(default_factory=list)
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    is_active: bool = True
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RescanResponse(BaseModel):
    message: str
    stats: Dict[str, Any]


class DiscoveredToolsRescanRequest(BaseModel):
    include_local: bool = True
    provider_instance_id: Optional[UUID] = None


class McpProbeToolItem(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    has_input_schema: bool
    has_output_schema: bool


class McpProbeResponse(BaseModel):
    provider_instance_id: UUID
    provider_slug: str
    provider_url: str
    tools_count: int
    tools: List[McpProbeToolItem] = Field(default_factory=list)


class McpOnboardRequest(BaseModel):
    provider_instance_id: UUID
    enable_all_in_runtime: bool = False
    include_local: bool = False


class McpOnboardResponse(BaseModel):
    provider_instance_id: UUID
    probe_tools_count: int
    rescan_stats: Dict[str, Any]
    linked_tools_updated: int
    active_discovered_tools: int
    published_tools: int


class DiscoveredToolUpdateRequest(BaseModel):
    tool_id: Optional[UUID] = Field(
        default=None,
        description="Publication container link. NULL means discovered-only capability.",
    )
