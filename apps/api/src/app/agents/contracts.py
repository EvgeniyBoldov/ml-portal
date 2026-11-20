"""Contracts for planner/executor protocol (runtime-safe DTOs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    OPERATION_CALL = "operation_call"
    AGENT_CALL = "agent_call"
    FINAL = "final"


class ExecutionModeType(str, Enum):
    DIRECT = "direct"
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


class ActionIntent(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    op: str = Field(..., min_length=1)


class OperationActionPayload(BaseModel):
    intent: ActionIntent
    input: Dict[str, Any] = Field(default_factory=dict)


class AgentActionPayload(BaseModel):
    agent_slug: str = Field(..., min_length=1)
    input: Dict[str, Any] = Field(default_factory=dict)


class FinalPayload(BaseModel):
    answer: str = Field(..., min_length=1)


class ActionMeta(BaseModel):
    side_effects: Optional[bool] = None
    risk_level: Optional[Literal["safe", "write", "destructive"]] = None
    why: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    finalization_rationale: Optional[str] = None


class ObservationStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"


class ObservationError(BaseModel):
    type: str
    message: str
    details: Optional[Dict[str, Any]] = None


class PolicyDecisionType(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_INPUT = "require_input"


class OperationAction(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    op: str = Field(..., min_length=1)
    name: Optional[str] = None
    scope: Literal["system", "collection"] = "collection"
    data_instance_slug: Optional[str] = None
    description: Optional[str] = None
    input_schema_hint: Optional[Dict[str, Any]] = None
    side_effects: bool = False
    risk_level: Literal["safe", "write", "destructive"] = "safe"
    idempotent: bool = True
    requires_confirmation: bool = False
    resource: Optional[str] = None
    systems: List[str] = Field(default_factory=list)


class AgentAction(BaseModel):
    agent_slug: str = Field(..., min_length=1)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    risk_level: Optional[str] = None


class AvailableActions(BaseModel):
    agents: List[AgentAction] = Field(default_factory=list)
    operations: List[OperationAction] = Field(default_factory=list)


@dataclass
class MissingRequirements:
    tools: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)

    @property
    def has_missing(self) -> bool:
        return bool(self.tools or self.collections or self.credentials)

    def to_message(self) -> str:
        parts: List[str] = []
        if self.tools:
            parts.append(f"Missing tools: {', '.join(self.tools)}")
        if self.collections:
            parts.append(f"Missing collections: {', '.join(self.collections)}")
        if self.credentials:
            parts.append(f"Missing credentials for: {', '.join(self.credentials)}")
        return "; ".join(parts)


class CollectionRuntimeStatus(str, Enum):
    READY = "ready"
    DEGRADED_MISSING_CREDENTIALS = "degraded_missing_credentials"
    DEGRADED_PROVIDER_UNHEALTHY = "degraded_provider_unhealthy"
    SCHEMA_STALE = "schema_stale"
    NO_OPERATIONS = "no_operations"


class CollectionRuntimeReadiness(BaseModel):
    collection_id: Optional[str] = None
    collection_slug: Optional[str] = None
    collection_type: Optional[str] = None
    current_version_id: Optional[str] = None
    current_version: Optional[int] = None
    current_version_status: Optional[str] = None
    schema_status: Optional[str] = None
    schema_freshness: Optional[str] = None
    data_instance_id: Optional[str] = None
    data_instance_slug: Optional[str] = None
    provider_instance_id: Optional[str] = None
    provider_instance_slug: Optional[str] = None
    provider_health: Optional[str] = None
    credential_status: Optional[str] = None
    available_operations: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    status: CollectionRuntimeStatus = CollectionRuntimeStatus.READY
    last_sync_at: Optional[str] = None


class PublishedOperationSummary(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    canonical_name: str = Field(..., min_length=1)
    scope_kind: Literal["system", "collection"] = "collection"
    domain: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    result_kind: Optional[str] = None
    collection_slug: Optional[str] = None
    # A canonical collection operation can be executable for more than one
    # collection.  The runtime keeps separate internal bindings, while
    # publication exposes one public operation plus its explicit targets.
    collection_slugs: List[str] = Field(default_factory=list)
    collection_type: Optional[str] = None
    collection_purpose: Optional[str] = None
    collection_readiness: Optional[str] = None
    schema_freshness: Optional[str] = None
    provider_kind: Optional[str] = None
    input_schema_summary: List[str] = Field(default_factory=list)
    side_effects: bool = False
    risk_level: Literal["safe", "write", "destructive"] = "safe"


class PublishedCollectionSummary(BaseModel):
    collection_slug: str = Field(..., min_length=1)
    collection_type: Optional[str] = None
    title: Optional[str] = None
    purpose: Optional[str] = None
    data_description: Optional[str] = None
    usage_rules: Optional[str] = None
    readiness_status: Optional[str] = None
    schema_freshness: Optional[str] = None
    missing_requirements: List[str] = Field(default_factory=list)
    available_operation_slugs: List[str] = Field(default_factory=list)
    available_operations: List[PublishedOperationSummary] = Field(default_factory=list)
    recommended_flow: List[str] = Field(default_factory=list)


class ResolvedDataInstance(BaseModel):
    instance_id: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    collection_id: Optional[str] = None
    collection_slug: Optional[str] = None
    instance_kind: Literal["data"] = "data"
    placement: Literal["local", "remote"]
    provider_instance_id: Optional[str] = None
    provider_instance_slug: Optional[str] = None
    # LLM-facing semantic description of the bound collection.
    # Source of truth: Collection.current_version.data_description.
    description: Optional[str] = None
    entity_type: Optional[str] = None
    collection_type: Optional[str] = None
    data_description: Optional[str] = None
    usage_purpose: Optional[str] = None
    usage_rules: Optional[str] = None
    remote_tables: List[str] = Field(default_factory=list)
    schema_fields: List[Dict[str, Any]] = Field(default_factory=list)
    readiness: Optional[CollectionRuntimeReadiness] = None


class ProviderExecutionTarget(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    provider_type: Literal["local", "mcp"]
    provider_instance_id: Optional[str] = None
    provider_instance_slug: Optional[str] = None
    provider_url: Optional[str] = None
    data_instance_id: str = Field(..., min_length=1)
    data_instance_slug: str = Field(..., min_length=1)
    handler_slug: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    timeout_s: Optional[int] = None
    has_credentials: bool = False
    credential_policy: Literal["not_required", "user_only", "user_tenant_platform"] = "user_tenant_platform"
    health_status: Optional[str] = None


class OperationCredentialContext(BaseModel):
    auth_type: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    credential_id: Optional[str] = None
    owner_type: Optional[str] = None


class ResolvedOperation(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    scope: Literal["system", "collection"] = "collection"
    description: Optional[str] = None
    # Raw discovered description for trace presentation; excluded from serialized runtime contracts.
    discovery_description: Optional[str] = Field(default=None, exclude=True)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    data_instance_id: str = Field(..., min_length=1)
    data_instance_slug: str = Field(..., min_length=1)
    collection_slug: Optional[str] = None
    provider_instance_id: Optional[str] = None
    provider_instance_slug: Optional[str] = None
    source: Literal["local", "mcp"]
    risk_level: Literal["safe", "write", "destructive"] = "safe"
    side_effects: bool = False
    idempotent: bool = True
    requires_confirmation: bool = False
    resource: Optional[str] = None
    systems: List[str] = Field(default_factory=list)
    return_summary: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    supports_partial_mode: bool = True
    raw_tool_slug: Optional[str] = None
    discovered_tool_id: Optional[str] = None
    published_domain: Optional[str] = None
    result_kind: Optional[str] = None
    result_delivery: Optional[Literal["direct", "store"]] = None
    observed_data_schema: Optional[Dict[str, Any]] = None
    sandbox_override_snapshot: Dict[str, Any] = Field(default_factory=dict)
    input_schema_summary: List[str] = Field(default_factory=list)
    published: Optional[PublishedOperationSummary] = None
    target: ProviderExecutionTarget


class OutlinePhase(BaseModel):
    phase_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    must_do: bool = True
    preferred_agents: List[str] = Field(default_factory=list)
    preferred_sources: List[str] = Field(default_factory=list)
    completion_signals: List[str] = Field(default_factory=list)
    allow_final_after: bool = False


class ExecutionOutline(BaseModel):
    mode: ExecutionModeType = ExecutionModeType.SINGLE_AGENT
    goal: str = Field(..., min_length=1)
    suggested_start_agent: Optional[str] = None
    phases: List[OutlinePhase] = Field(default_factory=list)
    finalization_rules: List[str] = Field(default_factory=list)
    clarify_triggers: List[str] = Field(default_factory=list)
    max_iterations: int = Field(default=6, ge=1, le=20)
    max_agent_handoffs: int = Field(default=3, ge=1, le=10)

