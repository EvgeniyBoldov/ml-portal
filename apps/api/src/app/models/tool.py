import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tool(Base):
    """
    Tool registry for LLM agents.
    Defines external capabilities (API calls, Python functions, etc.) with strict schemas.
    
    Примеры: jira.search, jira.create, rag.search, netbox.get_device
    """
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Unique identifier (e.g., "jira.search", "rag.search", "netbox.get_device")
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    # FK to ToolGroup (e.g., "jira", "rag", "netbox")
    tool_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Display name
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description for the LLM (what this tool does)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Tool type: 'api', 'function', 'database', etc.
    type: Mapped[str] = mapped_column(String(50), default="api", nullable=False)
    
    # JSON Schema for input arguments (The LLM uses this to call the tool)
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # JSON Schema for output (What the tool returns)
    output_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Execution configuration (e.g., HTTP URL, method, timeout, function_path)
    # Credentials should NOT be stored here in plain text ideally, but for MVP config is fine.
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    def __repr__(self):
        return f"<Tool {self.slug}>"
