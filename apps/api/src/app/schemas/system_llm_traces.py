"""
Pydantic schemas for SystemLLMTrace API.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class SystemLLMTraceBase(BaseModel):
    """Base schema for SystemLLMTrace."""
    trace_type: str = Field(..., description="Type of trace: planner or summary")
    role_config_id: UUID = Field(..., description="ID of the role configuration used")
    model: Optional[str] = Field(None, description="LLM model used")
    temperature: Optional[float] = Field(None, description="Temperature parameter used")
    max_tokens: Optional[int] = Field(None, description="Max tokens parameter used")
    duration_ms: Optional[int] = Field(None, description="Duration of the LLM call in milliseconds")
    attempt_number: Optional[int] = Field(None, description="Which attempt this was (1-based)")
    total_attempts: Optional[int] = Field(None, description="Total number of attempts")
    validation_status: str = Field(..., description="Validation status: success, failed, fallback_applied")
    result_type: Optional[str] = Field(None, description="Type of result: plan, agent, final, ask_user, text")
    result_summary: Optional[str] = Field(None, description="Brief summary of the result")
    fallback_applied: Optional[bool] = Field(None, description="Whether smart fallback was applied")
    validation_error: Optional[str] = Field(None, description="Validation error message if any")
    error: Optional[str] = Field(None, description="General error message if any")
    chat_id: Optional[UUID] = Field(None, description="Chat ID if available")
    tenant_id: Optional[UUID] = Field(None, description="Tenant ID if available")
    user_id: Optional[UUID] = Field(None, description="User ID if available")
    agent_run_id: Optional[UUID] = Field(None, description="Agent run ID if available")


class SystemLLMTraceCreate(SystemLLMTraceBase):
    """Schema for creating SystemLLMTrace."""
    compiled_prompt_hash: str = Field(..., description="Hash of the compiled prompt")
    compiled_prompt: Optional[str] = Field(None, description="Full compiled prompt text")
    structured_input: Dict[str, Any] = Field(..., description="Structured input sent to LLM")
    messages_sent: List[Dict[str, str]] = Field(..., description="Messages sent to LLM")
    raw_response: Optional[str] = Field(None, description="Raw response from LLM")
    parsed_response: Optional[Dict[str, Any]] = Field(None, description="Parsed JSON response")
    context_variables: Optional[Dict[str, Any]] = Field(None, description="Extracted context variables")
    fallback_details: Optional[Dict[str, Any]] = Field(None, description="Details of fallback if applied")


class SystemLLMTraceUpdate(BaseModel):
    """Schema for updating SystemLLMTrace."""
    # Most fields are immutable, but we might allow updating some metadata
    result_summary: Optional[str] = Field(None, description="Updated result summary")


class SystemLLMTraceResponse(SystemLLMTraceBase):
    """Schema for SystemLLMTrace response."""
    id: UUID = Field(..., description="Trace ID")
    created_at: datetime = Field(..., description="When the trace was created")
    updated_at: datetime = Field(..., description="When the trace was last updated")
    compiled_prompt_hash: str = Field(..., description="Hash of the compiled prompt")
    compiled_prompt: Optional[str] = Field(None, description="Full compiled prompt text")
    structured_input: Dict[str, Any] = Field(..., description="Structured input sent to LLM")
    messages_sent: List[Dict[str, str]] = Field(..., description="Messages sent to LLM")
    raw_response: Optional[str] = Field(None, description="Raw response from LLM")
    parsed_response: Optional[Dict[str, Any]] = Field(None, description="Parsed JSON response")
    context_variables: Optional[Dict[str, Any]] = Field(None, description="Extracted context variables")
    fallback_details: Optional[Dict[str, Any]] = Field(None, description="Details of fallback if applied")
    
    model_config = ConfigDict(from_attributes=True)


class SystemLLMTraceListResponse(BaseModel):
    """Schema for list of traces response."""
    traces: List[SystemLLMTraceResponse] = Field(..., description="List of traces")
    total: int = Field(..., description="Total number of traces")
    
    model_config = ConfigDict(from_attributes=True)


class TraceStatisticsResponse(BaseModel):
    """Schema for trace statistics response."""
    tenant_id: str = Field(..., description="Tenant ID")
    trace_type: Optional[str] = Field(None, description="Trace type filter")
    days: int = Field(..., description="Number of days analyzed")
    statistics: Dict[str, Any] = Field(..., description="Statistics data")
    
    model_config = ConfigDict(from_attributes=True)


class TraceAnalysisRequest(BaseModel):
    """Schema for trace analysis request."""
    trace_ids: List[UUID] = Field(..., description="List of trace IDs to analyze")
    analysis_type: str = Field(..., description="Type of analysis: performance, errors, patterns")


class TraceAnalysisResponse(BaseModel):
    """Schema for trace analysis response."""
    analysis_type: str = Field(..., description="Type of analysis performed")
    trace_count: int = Field(..., description="Number of traces analyzed")
    results: Dict[str, Any] = Field(..., description="Analysis results")
    insights: List[str] = Field(..., description="Key insights from the analysis")
    
    model_config = ConfigDict(from_attributes=True)
