"""
SystemLLMRole schemas for API.
"""
from typing import Optional, List, Dict, Any, Union, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.models.system_llm_role import SystemLLMRoleType
from app.schemas.runtime_limits import ActorLimitsResponse, OrchestratorLimitsUpdate


# === Base Schemas ===

class SystemLLMRoleBase(BaseModel):
    """Base schema for SystemLLMRole."""
    
    # === Role Identification ===
    role_type: SystemLLMRoleType = Field(..., description="Runtime role: planner | turn_preflight | synthesizer | memory | fact_extractor | fact_compactor")
    
    # === Prompt Parts ===
    identity: Optional[str] = Field(None, description="Role identity description")
    mission: Optional[str] = Field(None, description="Role mission and purpose")
    rules: Optional[str] = Field(None, description="Core rules and guidelines")
    safety: Optional[str] = Field(None, description="Safety constraints and rules")
    output_requirements: Optional[str] = Field(None, description="Output format and structure requirements")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Few-shot examples for the role")
    extras: Optional[Dict[str, Any]] = Field(None, description="Role-specific runtime knobs")
    
    # === Execution Configuration ===
    model: Optional[str] = Field(None, description="Model alias for this role")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature for LLM calls")
    
    # === Status ===
    is_active: Optional[bool] = Field(True, description="Whether this role configuration is active")


class ContractFailurePolicy(BaseModel):
    on_invalid: str = Field(..., description="Invalid output handling policy")


class JsonResponseContract(BaseModel):
    format: Literal["json"]
    schema: Dict[str, Any]
    plain_text: None = None
    markdown: None = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    examples_v2: Optional[Dict[str, Any]] = Field(default=None, description="Role examples grouped by input/outputs")
    failure_policy: ContractFailurePolicy
    format_locked: bool = Field(default=True, description="Whether the response format is locked (uneditable)")


class PlainTextResponseContract(BaseModel):
    format: Literal["plain_text"]
    schema: None = None
    plain_text: Dict[str, Any]
    markdown: None = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    examples_v2: Optional[Dict[str, Any]] = Field(default=None, description="Role examples grouped by input/outputs")
    failure_policy: ContractFailurePolicy
    format_locked: bool = Field(default=True, description="Whether the response format is locked (uneditable)")


class MarkdownResponseContract(BaseModel):
    format: Literal["markdown"]
    schema: None = None
    plain_text: None = None
    markdown: Dict[str, Any]
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    examples_v2: Optional[Dict[str, Any]] = Field(default=None, description="Role examples grouped by input/outputs")
    failure_policy: ContractFailurePolicy
    format_locked: bool = Field(default=True, description="Whether the response format is locked (uneditable)")


ResponseContract = Union[JsonResponseContract, PlainTextResponseContract, MarkdownResponseContract]


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
    extras: Optional[Dict[str, Any]] = Field(None, description="Role-specific runtime knobs")
    
    model: Optional[str] = Field(None, description="Model alias for this role")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature for LLM calls")
    
    is_active: Optional[bool] = Field(None, description="Whether this role configuration is active")


class SystemLLMRoleResponse(SystemLLMRoleBase):
    """Schema for SystemLLMRole response."""
    id: UUID
    response_contract: Optional[ResponseContract] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OrchestratorRoleSettingsUpdate(SystemLLMRoleUpdate):
    execution_limits: OrchestratorLimitsUpdate


class OrchestratorRoleSettingsResponse(BaseModel):
    role: SystemLLMRoleResponse
    execution_limits: ActorLimitsResponse


# All role-specific PATCH endpoints use SystemLLMRoleUpdate with real DB column
# names. Aliases keep the public service signatures readable.
PlannerRoleUpdate = SystemLLMRoleUpdate
SynthesizerRoleUpdate = SystemLLMRoleUpdate
FactExtractorRoleUpdate = SystemLLMRoleUpdate
FactCompactorRoleUpdate = SystemLLMRoleUpdate


# === Contract Schemas ===


# === Input Schemas ===

