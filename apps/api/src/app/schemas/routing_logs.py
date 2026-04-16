"""
Pydantic schemas for Routing Logs API.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class RoutingLogResponse(BaseModel):
    id: UUID
    run_id: UUID
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    request_text: Optional[str]
    intent: Optional[str]
    intent_confidence: Optional[float]
    selected_agent_slug: Optional[str]
    agent_confidence: Optional[float]
    routing_reasons: List[str]
    missing_tools: List[str]
    missing_collections: List[str]
    missing_credentials: List[str]
    execution_mode: Optional[str]
    effective_operations: List[str]
    effective_data_instances: List[str]
    operation_targets: Dict[str, Any]
    routed_at: datetime
    routing_duration_ms: Optional[int]
    status: str
    error_message: Optional[str]

    class Config:
        from_attributes = True
