"""
Audit Log model for tracking MCP and API requests.

Stores request/response data for observability and debugging.
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, DateTime, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """
    Audit log entry for API/MCP requests.
    
    Used for:
    - Debugging tool calls
    - Analyzing usage patterns
    - Security auditing
    - Cost tracking (tokens)
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Who made the request
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # What was requested
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "mcp.tools/call", "mcp.prompts/get"
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # e.g., tool slug, prompt slug
    
    # Request details (sanitized - no secrets)
    request_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Response summary
    response_status: Mapped[str] = mapped_column(String(50), default="success")  # success, error
    response_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metrics
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"
