"""
Tool model v2 - container for tool versions.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from enum import Enum
from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool_group import ToolGroup
    from app.models.tool_release import ToolBackendRelease, ToolRelease


class ToolKind(str, Enum):
    """Tool kind (v2)"""
    READ = "read"
    WRITE = "write"
    MIXED = "mixed"


class Tool(Base):
    """
    Tool container (v2).
    
    Примеры: jira.search, jira.create, rag.search, netbox.get_device
    
    Версионирование через ToolRelease (tool_version в v2 schema).
    current_version_id указывает на активную версию.
    """
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    tool_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # v2: current_version_id replaces recommended_release_id
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_releases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # v2: kind (read/write/mixed)
    kind: Mapped[str] = mapped_column(
        String(10), default=ToolKind.READ.value, nullable=False
    )
    
    # v2: tags for filtering
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
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
    
    current_version: Mapped[Optional["ToolRelease"]] = relationship(
        "ToolRelease",
        foreign_keys=[current_version_id],
        post_update=True
    )

    __table_args__ = (
        UniqueConstraint("tool_group_id", "slug", name="uq_tool_group_slug"),
    )

    def __repr__(self):
        return f"<Tool {self.slug}>"
