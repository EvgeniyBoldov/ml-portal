from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    """Configuration for a tool in agent"""
    tool_slug: str
    required: bool = False
    recommended: bool = False


class CollectionConfig(BaseModel):
    """Configuration for a collection in agent"""
    collection_slug: str
    required: bool = False
    recommended: bool = False


class AgentPolicy(BaseModel):
    """Agent execution policy"""
    execution: Optional[Dict[str, Any]] = Field(default=None, description="Execution limits: max_steps, max_tool_calls_total, etc")
    retry: Optional[Dict[str, Any]] = Field(default=None, description="Retry policy: max_retries, backoff_strategy")
    output: Optional[Dict[str, Any]] = Field(default=None, description="Output settings: citations_required, max_response_tokens")
    tool_execution: Optional[Dict[str, Any]] = Field(default=None, description="Tool execution: allow_parallel_tool_calls, batch_size")
    security: Optional[Dict[str, Any]] = Field(default=None, description="Security rules: allowed_models, block_sensitive_args")


class AgentBase(BaseModel):
    slug: str = Field(..., description="Unique identifier", example="netbox-helper")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    system_prompt_slug: str = Field(..., description="Slug of the System Prompt")
    baseline_prompt_id: Optional[UUID] = Field(default=None, description="ID of the Baseline Prompt (restrictions)")
    tools: List[str] = Field(default=[], description="List of Tool slugs (legacy)")
    available_collections: List[str] = Field(default=[], description="List of Collection slugs (legacy)")
    tools_config: List[ToolConfig] = Field(default=[], description="Structured tools configuration")
    collections_config: List[CollectionConfig] = Field(default=[], description="Structured collections configuration")
    policy: Optional[AgentPolicy] = Field(default=None, description="Execution policy")
    capabilities: List[str] = Field(default=[], description="Agent capabilities for Router matching")
    supports_partial_mode: bool = Field(default=False, description="Allow partial execution if some tools unavailable")
    generation_config: Optional[Dict[str, Any]] = {}
    is_active: bool = True
    enable_logging: bool = Field(default=True, description="Enable detailed run logging")


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt_slug: Optional[str] = None
    baseline_prompt_id: Optional[UUID] = None
    tools: Optional[List[str]] = None
    available_collections: Optional[List[str]] = None
    tools_config: Optional[List[ToolConfig]] = None
    collections_config: Optional[List[CollectionConfig]] = None
    policy: Optional[AgentPolicy] = None
    capabilities: Optional[List[str]] = None
    supports_partial_mode: Optional[bool] = None
    generation_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    enable_logging: Optional[bool] = None


class AgentResponse(AgentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
