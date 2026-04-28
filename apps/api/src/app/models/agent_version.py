"""
AgentVersion model - versioned agent configuration.

Architecture (v2):
- Agent (container) - holds metadata, model, generation params, safety config
- AgentVersion - holds prompt parts and routing fields only
Version statuses:
- draft: can be edited, can be published
- published: used in runtime (only one per agent)
- archived: no longer used, kept for history
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from sqlalchemy import String, DateTime, Text, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentVersionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AgentVersion(Base):
    """
    Agent version - holds structured prompt parts, execution config, safety knobs, and routing fields.

    Only one version per agent can be PUBLISHED at a time.
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

    # ── Prompt parts (structured, each column) ──────────────────────────
    identity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mission: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_use_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    examples: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Safety prompt constraints (version-specific text, not config) ────────────────
    never_do: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_ops: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Routing (for agent router) ────────────────────────────────────────
    short_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    is_routable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    routing_keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    routing_negative_keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

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

    @property
    def compiled_prompt(self) -> str:
        """Assemble prompt parts into a single system prompt string."""
        parts = []
        if self.identity:
            parts.append(f"# Identity\n{self.identity}")
        if self.mission:
            parts.append(f"# Mission\n{self.mission}")
        if self.scope:
            parts.append(f"# Scope\n{self.scope}")
        if self.rules:
            parts.append(f"# Rules\n{self.rules}")
        if self.tool_use_rules:
            parts.append(f"# Tool Use Rules\n{self.tool_use_rules}")
        if self.output_format:
            parts.append(f"# Output Format\n{self.output_format}")
        if self.examples:
            parts.append(f"# Examples\n{self.examples}")
        if self.never_do:
            parts.append(f"# ЗАПРЕЩЕНО\n{self.never_do}")
        if self.allowed_ops:
            parts.append(f"# РАЗРЕШЁННЫЕ ОПЕРАЦИИ\n{self.allowed_ops}")
        return "\n\n".join(parts) if parts else ""

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

    @property
    def is_editable(self) -> bool:
        return self.status == AgentVersionStatus.DRAFT.value

    @property
    def can_publish(self) -> bool:
        return self.status == AgentVersionStatus.DRAFT.value

    @property
    def can_archive(self) -> bool:
        return self.status == AgentVersionStatus.PUBLISHED.value

    def __repr__(self) -> str:
        return f"<AgentVersion {self.agent_id} v{self.version} ({self.status})>"
