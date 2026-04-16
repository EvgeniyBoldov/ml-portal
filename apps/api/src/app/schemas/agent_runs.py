from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AgentRunStepResponse(BaseModel):
    """Single step within an agent run"""
    id: UUID
    step_number: int
    step_type: str = Field(
        ...,
        description="user_request, routing, llm_request, llm_response, "
                    "tool_call, tool_result, final_response, error"
    )
    data: Dict[str, Any] = Field(default={})
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    """Agent run summary"""
    id: UUID
    chat_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    tenant_id: UUID
    agent_slug: str
    logging_level: str = Field(default="brief", description="none, brief, full")
    status: str = Field(..., description="running, completed, failed")
    context_snapshot: Optional[Dict[str, Any]] = None
    total_steps: int = 0
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentRunDetailResponse(AgentRunResponse):
    """Agent run with all steps"""
    steps: List[AgentRunStepResponse] = []


class AgentRunListResponse(BaseModel):
    """Paginated list of agent runs"""
    items: List[AgentRunResponse]
    total: int
    page: int
    page_size: int


class AgentRunTracePackResponse(BaseModel):
    """Deterministic trace pack for replay/debug."""
    run_id: UUID
    agent_slug: str
    status: str
    logging_level: str
    context_snapshot: Optional[Dict[str, Any]] = None
    operations: List[str] = []
    prompt_surfaces: List[Dict[str, Any]] = []
    tool_io: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    timeline: List[Dict[str, Any]] = []
    total_steps: int = 0


class CapabilityGraphNodeResponse(BaseModel):
    id: str
    type: str
    label: str
    meta: Dict[str, Any] = {}


class CapabilityGraphEdgeResponse(BaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    type: str
    meta: Dict[str, Any] = {}

    class Config:
        populate_by_name = True


class RuntimeCapabilityGraphResponse(BaseModel):
    tenant_id: UUID
    user_id: UUID
    agent_slug: Optional[str] = None
    nodes: List[CapabilityGraphNodeResponse] = []
    edges: List[CapabilityGraphEdgeResponse] = []
    stats: Dict[str, int] = {}
    missing: Dict[str, List[str]] = {}


class RuntimeHitlConditionResponse(BaseModel):
    condition_id: str
    decision: str
    when: str
    reason: str


class RuntimeOperationPolicyResponse(BaseModel):
    operation_slug: str
    operation: str
    name: str
    side_effects: str
    risk_level: str
    requires_confirmation_semantic: bool
    effective_decision: str
    reasons: List[str] = []


class RuntimeHitlPolicyContractResponse(BaseModel):
    tenant_id: UUID
    user_id: UUID
    global_: Dict[str, Any] = Field(alias="global")
    conditions: List[RuntimeHitlConditionResponse] = []
    operation_policies: List[RuntimeOperationPolicyResponse] = []
    resume_contract: Dict[str, Any] = {}

    class Config:
        populate_by_name = True


class AgentRunFilter(BaseModel):
    """Filter options for agent runs"""
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    agent_slug: Optional[str] = None
    status: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
