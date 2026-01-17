"""
API Token model for MCP/IDE authentication
"""
from __future__ import annotations
from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid

from .base import Base


class ApiToken(Base):
    """API tokens for programmatic access (MCP, IDE, etc.)"""
    __tablename__ = "api_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(10), nullable=False)  # First 8 chars for identification
    
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Comma-separated scopes: mcp,chat,rag
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
