"""
ToolGroup model v2 - группировка инструментов
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool import Tool
    from app.models.tool_instance import ToolInstance


class ToolGroup(Base):
    """
    Группа инструментов (v2).
    
    Примеры: jira, rag, netbox, cmdb, remedy, collection
    """
    __tablename__ = "tool_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # v2: type (jira/crm/etc) and description for agent router
    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description_for_router: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    
    # Relationships
    tools: Mapped[List["Tool"]] = relationship(
        "Tool",
        back_populates="tool_group",
        foreign_keys="Tool.tool_group_id",
        cascade="all, delete-orphan"
    )
    
    instances: Mapped[List["ToolInstance"]] = relationship(
        "ToolInstance",
        back_populates="tool_group",
        foreign_keys="ToolInstance.tool_group_id",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ToolGroup {self.slug}>"
