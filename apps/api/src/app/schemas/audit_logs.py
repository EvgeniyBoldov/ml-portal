"""
Pydantic schemas for Audit Logs API.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[str]
    tenant_id: Optional[str]
    action: str
    resource: Optional[str]
    request_data: Optional[dict]
    response_status: str
    response_data: Optional[dict]
    error_message: Optional[str]
    duration_ms: Optional[int]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int


class AuditLogStats(BaseModel):
    total_requests: int
    success_count: int
    error_count: int
    avg_duration_ms: Optional[float]
    total_tokens_in: int
    total_tokens_out: int
    top_actions: List[dict]
    top_users: List[dict]
