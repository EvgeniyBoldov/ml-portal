"""
ToolInstance model v2 - конкретное подключение к системе
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool_group import ToolGroup


class ToolInstance(Base):
    """
    Конкретный instance системы с настройками подключения (v2).
    
    Примеры:
    - jira-prod (url: https://jira.company.com)
    - netbox-main (url: https://netbox.company.com)
    
    Креды привязываются через Credential (owner-based).
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
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # v2: explicit url field
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
        UniqueConstraint("tool_group_id", "url", name="uq_tool_instance_group_url"),
    )

    def __repr__(self) -> str:
        return f"<ToolInstance {self.name}>"
