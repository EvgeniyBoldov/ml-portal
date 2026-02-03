import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool_group import ToolGroup
    from app.models.tool_release import ToolBackendRelease, ToolRelease


class Tool(Base):
    """
    Tool registry for LLM agents.
    Defines external capabilities (API calls, Python functions, etc.) with strict schemas.
    
    Примеры: jira.search, jira.create, rag.search, netbox.get_device
    
    Версионирование:
    - backend_releases: версии из кода (заполняются воркером)
    - releases: версии для агентов (создаются через UI)
    - recommended_release_id: основная версия для использования
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
    
    # Name for LLM (how to refer to this tool in prompts)
    name_for_llm: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Description for the LLM (what this tool does)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Tool type: 'builtin', 'api', 'function', 'database', etc.
    type: Mapped[str] = mapped_column(String(50), default="builtin", nullable=False)
    
    # JSON Schema for input arguments (legacy, now in backend_releases)
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # JSON Schema for output (legacy, now in backend_releases)
    output_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Execution configuration (e.g., HTTP URL, method, timeout, function_path)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Recommended release for agents to use
    recommended_release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_releases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
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
    
    # Relationships
    tool_group: Mapped["ToolGroup"] = relationship(
        "ToolGroup",
        back_populates="tools",
        foreign_keys=[tool_group_id]
    )
    
    backend_releases: Mapped[List["ToolBackendRelease"]] = relationship(
        "ToolBackendRelease",
        back_populates="tool",
        foreign_keys="ToolBackendRelease.tool_id",
        cascade="all, delete-orphan"
    )
    
    releases: Mapped[List["ToolRelease"]] = relationship(
        "ToolRelease",
        back_populates="tool",
        foreign_keys="ToolRelease.tool_id",
        cascade="all, delete-orphan"
    )
    
    recommended_release: Mapped[Optional["ToolRelease"]] = relationship(
        "ToolRelease",
        foreign_keys=[recommended_release_id],
        post_update=True
    )

    def __repr__(self):
        return f"<Tool {self.slug}>"
