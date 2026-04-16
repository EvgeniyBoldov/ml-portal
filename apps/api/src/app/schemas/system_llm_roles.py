"""
SystemLLMRole schemas for API.
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.system_llm_role import SystemLLMRoleType, RetryBackoffType
from app.agents.contracts import ExecutionModeType


# === Base Schemas ===

class SystemLLMRoleBase(BaseModel):
    """Base schema for SystemLLMRole."""
    
    # === Role Identification ===
    role_type: SystemLLMRoleType = Field(..., description="Role type: triage | planner | summary | memory")
    
    # === Prompt Parts ===
    identity: Optional[str] = Field(None, description="Role identity description")
    mission: Optional[str] = Field(None, description="Role mission and purpose")
    rules: Optional[str] = Field(None, description="Core rules and guidelines")
    safety: Optional[str] = Field(None, description="Safety constraints and rules")
    output_requirements: Optional[str] = Field(None, description="Output format and structure requirements")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Few-shot examples for the role")
    
    # === Execution Configuration ===
    model: Optional[str] = Field(None, description="Model alias for this role")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature for LLM calls")
    max_tokens: Optional[int] = Field(None, gt=0, description="Maximum tokens for LLM response")
    timeout_s: Optional[int] = Field(None, gt=0, description="Timeout in seconds")
    max_retries: Optional[int] = Field(None, ge=0, description="Maximum retry attempts")
    retry_backoff: Optional[RetryBackoffType] = Field(None, description="Retry backoff strategy")
    
    # === Status ===
    is_active: Optional[bool] = Field(True, description="Whether this role configuration is active")


class SystemLLMRoleCreate(SystemLLMRoleBase):
    """Schema for creating SystemLLMRole."""
    pass


class SystemLLMRoleUpdate(BaseModel):
    """Schema for updating SystemLLMRole."""
    identity: Optional[str] = Field(None, description="Role identity description")
    mission: Optional[str] = Field(None, description="Role mission and purpose")
    rules: Optional[str] = Field(None, description="Core rules and guidelines")
    safety: Optional[str] = Field(None, description="Safety constraints and rules")
    output_requirements: Optional[str] = Field(None, description="Output format and structure requirements")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Few-shot examples for the role")
    
    model: Optional[str] = Field(None, description="Model alias for this role")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature for LLM calls")
    max_tokens: Optional[int] = Field(None, gt=0, description="Maximum tokens for LLM response")
    timeout_s: Optional[int] = Field(None, gt=0, description="Timeout in seconds")
    max_retries: Optional[int] = Field(None, ge=0, description="Maximum retry attempts")
    retry_backoff: Optional[RetryBackoffType] = Field(None, description="Retry backoff strategy")
    
    is_active: Optional[bool] = Field(None, description="Whether this role configuration is active")


class SystemLLMRoleResponse(SystemLLMRoleBase):
    """Schema for SystemLLMRole response."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# TriageRoleUpdate, PlannerRoleUpdate, SummaryRoleUpdate, MemoryRoleUpdate removed.
# All role-specific PATCH endpoints now use SystemLLMRoleUpdate directly
# with real DB column names: identity, mission, rules, safety, output_requirements.
# Backward compat aliases for imports:
TriageRoleUpdate = SystemLLMRoleUpdate
PlannerRoleUpdate = SystemLLMRoleUpdate
SummaryRoleUpdate = SystemLLMRoleUpdate
MemoryRoleUpdate = SystemLLMRoleUpdate


# === Contract Schemas ===

class TriageDecision(BaseModel):
    """Triage decision contract."""
    type: str = Field(..., pattern="^(final|clarify|orchestrate)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., description="Explanation of the decision")
    
    # Conditional fields
    answer: Optional[str] = Field(None, description="Answer if type=final")
    clarify_prompt: Optional[str] = Field(None, description="Prompt if type=clarify")
    goal: Optional[str] = Field(None, description="Goal if type=orchestrate")
    inputs: Optional[Dict[str, Any]] = Field(None, description="Input data if type=orchestrate")


class ExecutionOutlinePhase(BaseModel):
    """High-level phase for orchestration guidance."""
    phase_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    must_do: bool = True
    preferred_agents: List[str] = Field(default_factory=list)
    preferred_sources: List[str] = Field(default_factory=list)
    completion_signals: List[str] = Field(default_factory=list)
    allow_final_after: bool = False


class ExecutionOutline(BaseModel):
    """High-level orchestration outline returned by helper/planner-compatible layers."""
    mode: ExecutionModeType = ExecutionModeType.SINGLE_AGENT
    goal: str = Field(..., min_length=1)
    suggested_start_agent: Optional[str] = None
    phases: List[ExecutionOutlinePhase] = Field(default_factory=list)
    finalization_rules: List[str] = Field(default_factory=list)
    clarify_triggers: List[str] = Field(default_factory=list)
    max_iterations: int = Field(default=6, ge=1, le=20)
    max_agent_handoffs: int = Field(default=3, ge=1, le=10)


class HelperSummaryPayload(BaseModel):
    """Structured helper summary used to compress runtime context."""
    goal: Optional[str] = None
    facts: List[str] = Field(default_factory=list)
    checked_sources: List[str] = Field(default_factory=list)
    checked_agents: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    partial_conclusions: List[str] = Field(default_factory=list)
    unresolved_risks: List[str] = Field(default_factory=list)


class PlannerStep(BaseModel):
    """Individual step in planner execution."""
    step_id: str = Field(default="s1", description="Unique step identifier")
    title: str = Field(..., description="Step title")
    kind: str = Field(..., pattern="^(agent|operation|llm|ask_user)$")
    ref: Optional[str] = Field(None, description="Reference to agent/operation")
    op: Optional[str] = Field(None, description="Operation to perform")
    input: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Step input data")
    requires_confirmation: bool = Field(default=False, description="Whether step requires confirmation")
    risk_level: str = Field(default="low", pattern="^(low|medium|high|destructive)$")
    on_fail: str = Field(default="retry", pattern="^(retry|replan|ask_user|abort)$")


class PlannerPlan(BaseModel):
    """Planner execution plan contract."""
    goal: str = Field(default="", description="Overall goal")
    steps: List[PlannerStep] = Field(..., description="Execution steps")


# === Input Schemas ===

class TriageInput(BaseModel):
    """Structured input for Triage role."""
    user_message: str = Field(..., description="Current user message")
    conversation_summary: Optional[str] = Field(None, description="Summary of conversation")
    session_state: Dict[str, Any] = Field(default_factory=dict, description="Session state")
    available_agents: List[Dict[str, Any]] = Field(default_factory=list, description="Available agents")
    policies: Optional[str] = Field(None, description="Security policies")
    active_run: Optional[Dict[str, Any]] = Field(None, description="Currently active run")


class PlannerInput(BaseModel):
    """Structured input for Planner role."""
    goal: str = Field(..., description="Goal to plan")
    conversation_summary: Optional[str] = Field(None, description="Summary of conversation")
    session_state: Dict[str, Any] = Field(default_factory=dict, description="Session state")
    available_agents: List[Dict[str, Any]] = Field(default_factory=list, description="Available agents")
    available_operations: List[Dict[str, Any]] = Field(default_factory=list, description="Available operations")
    policies: Optional[str] = Field(None, description="Security policies")
    execution_outline: Optional[ExecutionOutline] = Field(None, description="Execution outline with phased hints")


class SummaryInput(BaseModel):
    """Structured input for Summary role."""
    previous_summary: Optional[str] = Field(None, description="Previous conversation summary")
    recent_messages: List[Dict[str, Any]] = Field(default_factory=list, description="Recent messages to summarize")
    current_user_message: Optional[str] = Field(None, description="Current user message for the turn")
    current_agent_response: Optional[str] = Field(None, description="Current agent response for the turn")
    execution_memory: Optional[Dict[str, Any]] = Field(None, description="Execution memory snapshot, if available")
    session_state: Dict[str, Any] = Field(default_factory=dict, description="Session state")
