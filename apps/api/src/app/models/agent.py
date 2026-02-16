"""
Agent model v2 - versioned agent container.

Architecture:
- Agent (container) - holds metadata: slug, name, description, current_version_id
- AgentVersion - holds versioned data: prompt, policy_id, limit_id
- AgentBinding (tool_bind) links to agent_version_id
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

import enum


class LoggingLevel(str, enum.Enum):
    """Agent logging verbosity level"""
    NONE = "none"
    BRIEF = "brief"
    FULL = "full"

from app.models.base import Base


class Agent(Base):
    """
    Agent container - holds metadata for an agent.

    Each agent can have multiple versions (AgentVersion).
    current_version_id points to the active version.
    """
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    routing_example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_routable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agent_versions.id', ondelete='SET NULL', use_alter=True),
        nullable=True,
        index=True
    )

    logging_level: Mapped[str] = mapped_column(
        String(10),
        default=LoggingLevel.BRIEF.value,
        nullable=False,
        server_default="brief",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    versions: Mapped[List["AgentVersion"]] = relationship(
        "AgentVersion",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(AgentVersion.version)",
        foreign_keys="AgentVersion.agent_id"
    )

    current_version: Mapped[Optional["AgentVersion"]] = relationship(
        "AgentVersion",
        foreign_keys=[current_version_id],
        post_update=True
    )

    def __repr__(self):
        return f"<Agent {self.slug}>"
