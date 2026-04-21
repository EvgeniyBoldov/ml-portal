"""Contracts for planner/executor protocol (runtime-safe DTOs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    OPERATION_CALL = "operation_call"
    AGENT_CALL = "agent_call"
    ASK_USER = "ask_user"
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


class AskUserPayload(BaseModel):
    question: str = Field(..., min_length=1)


class FinalPayload(BaseModel):
    answer: str = Field(..., min_length=1)


class ActionMeta(BaseModel):
    side_effects: Optional[bool] = None
    risk_level: Optional[Literal["safe", "write", "destructive"]] = None
    why: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    finalization_rationale: Optional[str] = None


class NextAction(BaseModel):
    type: ActionType
    operation: Optional[OperationActionPayload] = None
    agent: Optional[AgentActionPayload] = None
    ask_user: Optional[AskUserPayload] = None
    final: Optional[FinalPayload] = None
    meta: Optional[ActionMeta] = None


class ObservationStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"


class ObservationError(BaseModel):
    type: str
    message: str
    details: Optional[Dict[str, Any]] = None


class Observation(BaseModel):
    status: ObservationStatus
    summary: str = Field(..., min_length=1)
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[ObservationError] = None


class PolicyDecisionType(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_INPUT = "require_input"


class PolicyDecision(BaseModel):
    decision: PolicyDecisionType
    reason: str = Field(..., min_length=1)


class OperationAction(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    op: str = Field(..., min_length=1)
    name: Optional[str] = None
    data_instance_slug: Optional[str] = None
    description: Optional[str] = None
    input_schema_hint: Optional[Dict[str, Any]] = None
    side_effects: bool = False
    risk_level: Literal["safe", "write", "destructive"] = "safe"
    idempotent: bool = True
    requires_confirmation: bool = False
    credential_scope: Literal["platform", "user", "auto"] = "auto"
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
class ToolCapability:
    tool_slug: str
    instance_id: Optional[str] = None
    instance_slug: Optional[str] = None
    has_credentials: bool = False
    required: bool = False
    recommended: bool = False


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
    # LLM-facing description of the collection / data asset.
    # Source of truth: Collection.description on the bound collection (nullable).
    description: Optional[str] = None
    entity_type: Optional[str] = None


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
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    data_instance_id: str = Field(..., min_length=1)
    data_instance_slug: str = Field(..., min_length=1)
    provider_instance_id: Optional[str] = None
    provider_instance_slug: Optional[str] = None
    source: Literal["local", "mcp"]
    risk_level: Literal["safe", "write", "destructive"] = "safe"
    side_effects: bool = False
    idempotent: bool = True
    requires_confirmation: bool = False
    credential_scope: Literal["platform", "user", "auto"] = "auto"
    resource: Optional[str] = None
    systems: List[str] = Field(default_factory=list)
    return_summary: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    supports_partial_mode: bool = True
    target: ProviderExecutionTarget


class HelperSummary(BaseModel):
    goal: Optional[str] = None
    facts: List[str] = Field(default_factory=list)
    checked_sources: List[str] = Field(default_factory=list)
    checked_agents: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    partial_conclusions: List[str] = Field(default_factory=list)
    unresolved_risks: List[str] = Field(default_factory=list)


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


class OutlineProgress(BaseModel):
    current_phase_id: Optional[str] = None
    completed_phase_ids: List[str] = Field(default_factory=list)
    phase_notes: Dict[str, List[str]] = Field(default_factory=dict)
    blocked_phase_ids: List[str] = Field(default_factory=list)

    def is_phase_completed(self, phase_id: str) -> bool:
        return phase_id in self.completed_phase_ids

    def mark_phase_completed(self, phase_id: str) -> None:
        if phase_id not in self.completed_phase_ids:
            self.completed_phase_ids.append(phase_id)

    def add_phase_note(self, phase_id: str, note: str) -> None:
        if not note:
            return
        notes = self.phase_notes.setdefault(phase_id, [])
        if note not in notes:
            notes.append(note)


class StopReason(str, Enum):
    DONE = "done"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    FAILED = "failed"
    MAX_ITERS = "max_iters"
    LOOP_DETECTED = "loop_detected"


class RuntimePipelineRequest(BaseModel):
    """Unified input contract for runtime pipeline execution."""

    request_text: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    agent_slug: Optional[str] = None
    agent_version_id: Optional[str] = None
    model: Optional[str] = None


class RuntimeTriageDecision(BaseModel):
    """Normalized triage result used by runtime pipeline."""

    type: Literal["final", "clarify", "orchestrate"]
    confidence: float = 0.0
    answer: Optional[str] = None
    clarify_prompt: Optional[str] = None
    goal: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None


@dataclass
class RuntimeExecutionSnapshot:
    """Precomputed runtime context shared across triage/preflight/planner."""

    effective_permissions: Any
    routable_agents: List[Any] = field(default_factory=list)
    denied_routable_agents: List[str] = field(default_factory=list)
