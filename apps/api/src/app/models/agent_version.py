"""
AgentVersion model - versioned agent configuration.

Architecture (v2):
- Agent (container) - holds metadata: slug, name, description, current_version_id
- AgentVersion - holds versioned data: prompt, policy_id, limit_id
- ToolBind (AgentBinding) links to agent_version_id

Version statuses:
- draft: can be edited, can be activated
- active: used in runtime (only one per agent)
- deprecated: no longer used, kept for history
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentVersionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class AgentVersion(Base):
    """
    Agent version - holds prompt text, policy and limit references.

    Each version belongs to an Agent and contains:
    - prompt: System prompt text for the agent
    - policy_id: Optional reference to Policy (behavioral rules)
    - limit_id: Optional reference to Limit (execution constraints)

    Only one version per agent can be ACTIVE at a time.
    Tool bindings (AgentBinding) are linked to agent_version_id.
    """
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint('agent_id', 'version', name='uix_agent_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agents.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default=AgentVersionStatus.DRAFT.value,
        nullable=False,
        index=True
    )

    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('policies.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    limit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('limits.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agent_versions.id', ondelete='SET NULL'),
        nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="versions",
        foreign_keys=[agent_id]
    )

    parent_version: Mapped[Optional["AgentVersion"]] = relationship(
        "AgentVersion",
        remote_side=[id],
        foreign_keys=[parent_version_id]
    )

    bindings: Mapped[List["AgentBinding"]] = relationship(
        "AgentBinding",
        back_populates="agent_version",
        cascade="all, delete-orphan"
    )

    @property
    def is_editable(self) -> bool:
        return self.status == AgentVersionStatus.DRAFT.value

    @property
    def can_activate(self) -> bool:
        return self.status == AgentVersionStatus.DRAFT.value

    @property
    def can_deactivate(self) -> bool:
        return self.status in (AgentVersionStatus.DRAFT.value, AgentVersionStatus.ACTIVE.value)

    def __repr__(self) -> str:
        return f"<AgentVersion {self.agent_id} v{self.version} ({self.status})>"
