"""
ToolInstance model v2 - конкретное подключение к системе

Instance types:
- LOCAL: auto-managed by backend (RAG, collections). Cannot be created/deleted from UI.
  No credentials needed.
- REMOTE: user-created external systems (jira, netbox, crm). Managed via UI.
  Credentials required.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool_group import ToolGroup


class InstanceType(str, Enum):
    """Instance type: local (auto-managed) or remote (user-managed)"""
    LOCAL = "local"
    REMOTE = "remote"


class ToolInstance(Base):
    """
    Конкретный instance системы с настройками подключения (v2).
    
    LOCAL instances (auto-managed):
    - rag-global (RAG knowledge base, scope=global)
    - collection-{slug} (per-collection, auto-created/deleted)
    
    REMOTE instances (user-managed):
    - jira-prod (url: https://jira.company.com)
    - netbox-main (url: https://netbox.company.com)
    
    Креды привязываются через Credential (owner-based).
    Локальные инстансы не требуют кредов.
    """
    __tablename__ = "tool_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # FK to ToolGroup (e.g., "jira", "rag", "netbox")
    tool_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Instance type: local (auto-managed) or remote (user-managed)
    instance_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default='remote'
    )
    
    # Category tag for filtering (collection, rag, llm, dcbox, jira, etc.)
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
        comment="Instance category tag for filtering"
    )
    
    # v2: explicit url field (empty for local instances)
    url: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    
    # Additional config (project mappings, timeouts, etc.)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    health_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    
    # Relationships
    tool_group: Mapped["ToolGroup"] = relationship(
        "ToolGroup",
        back_populates="instances",
        foreign_keys=[tool_group_id]
    )

    __table_args__ = (
        UniqueConstraint("tool_group_id", "slug", name="uq_tool_instance_group_slug"),
        CheckConstraint(
            "instance_type IN ('local', 'remote')",
            name="ck_tool_instance_type"
        ),
    )

    def __repr__(self) -> str:
        return f"<ToolInstance {self.name}>"
