"""
ToolGroup model - группировка инструментов для UI и организации
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ToolGroup(Base):
    """
    Группа инструментов для организации и UI.
    
    Примеры: jira, rag, netbox, cmdb, remedy, collection
    Используется для группировки инструментов и инстансов.
    Не используется для прав доступа.
    """
    __tablename__ = "tool_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Unique identifier (e.g., "jira", "rag", "netbox")
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    
    # Display name
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
        return f"<ToolGroup {self.slug}>"
