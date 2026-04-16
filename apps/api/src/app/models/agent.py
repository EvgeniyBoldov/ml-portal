"""
Agent model v2 - versioned agent container.

Architecture:
- Agent (container) - holds metadata + model selection + collection bindings
- AgentVersion - holds prompt parts, execution config, safety knobs, and routing fields
- Runtime routing is resolved by operation metadata and bindings.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

import enum

from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LoggingLevel(str, enum.Enum):
    """Agent logging verbosity level"""
    NONE = "none"
    BRIEF = "brief"
    FULL = "full"


class Agent(Base):
    """
    Agent container - holds human-readable metadata.

    Each agent can have multiple versions (AgentVersion).
    current_version_id points to the published version.
    Routing metadata is stored in AgentVersion.
    """
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Info (for humans) ───────────────────────────────────────────────
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Catalog metadata ───────────────────────────────────────────────────
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agent_versions.id', ondelete='SET NULL', use_alter=True),
        nullable=True,
        index=True
    )

    allowed_collection_ids: Mapped[Optional[List[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="Whitelist of Collection IDs bound to this agent container. NULL = all collections allowed by RBAC."
    )

    logging_level: Mapped[str] = mapped_column(
        String(10),
        default=LoggingLevel.BRIEF.value,
        nullable=False,
        server_default="brief",
    )

    # ── Model selection (extracted from AgentVersion) ──────────────────
    model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Default model fallback for this agent container (AgentVersion.model -> Agent.model -> orchestration default)"
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
