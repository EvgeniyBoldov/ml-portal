"""
AgentBinding model v2 - tool bindings per agent version.

Links AgentVersion to Tool + ToolInstance with credential strategy.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CredentialStrategy(str, Enum):
    """
    Стратегия выбора кредов для инструмента (v2).

    USER_ONLY - только креды пользователя
    TENANT_ONLY - только креды тенанта
    PLATFORM_ONLY - только платформенные креды
    USER_THEN_TENANT - user > tenant
    TENANT_THEN_PLATFORM - tenant > platform
    ANY - первый доступный
    """
    USER_ONLY = "USER_ONLY"
    TENANT_ONLY = "TENANT_ONLY"
    PLATFORM_ONLY = "PLATFORM_ONLY"
    USER_THEN_TENANT = "USER_THEN_TENANT"
    TENANT_THEN_PLATFORM = "TENANT_THEN_PLATFORM"
    ANY = "ANY"


class AgentBinding(Base):
    """
    Tool binding per agent version (v2 tool_bind).

    Links AgentVersion → Tool + ToolInstance.
    Defines credential resolution strategy.
    """
    __tablename__ = "agent_bindings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # FK to AgentVersion (v2: bindings belong to version, not agent)
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # FK to Tool
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # FK to ToolInstance (NULL = not bound to specific instance)
    tool_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    credential_strategy: Mapped[str] = mapped_column(
        String(30),
        default=CredentialStrategy.ANY.value,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    agent_version: Mapped["AgentVersion"] = relationship(
        "AgentVersion",
        back_populates="bindings"
    )

    __table_args__ = (
        UniqueConstraint("agent_version_id", "tool_id", name="uq_agent_version_tool"),
    )

    def __repr__(self):
        return f"<AgentBinding version={self.agent_version_id} tool={self.tool_id}>"
