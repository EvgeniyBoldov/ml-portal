"""
Limit model - execution limits for agents.

Architecture:
- Limit (container) - holds metadata: slug, name, description
- LimitVersion - holds versioned data: max_steps, timeouts, budgets
- current_version_id - points to the active version

Version statuses:
- draft: can be edited, can be activated
- active: used by agents (only one per limit)
- deprecated: no longer used, kept for history
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LimitStatus(str, Enum):
    """Limit version status"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class Limit(Base):
    """
    Limit container - holds metadata for execution limits.

    Each limit can have multiple versions (LimitVersion).
    current_version_id points to the active version.
    """
    __tablename__ = "limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('limit_versions.id', ondelete='SET NULL', use_alter=True),
        nullable=True,
        index=True
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

    versions: Mapped[List["LimitVersion"]] = relationship(
        "LimitVersion",
        back_populates="limit",
        cascade="all, delete-orphan",
        order_by="desc(LimitVersion.version)",
        foreign_keys="LimitVersion.limit_id"
    )

    current_version: Mapped[Optional["LimitVersion"]] = relationship(
        "LimitVersion",
        foreign_keys=[current_version_id],
        post_update=True
    )

    def __repr__(self) -> str:
        return f"<Limit {self.slug}>"


class LimitVersion(Base):
    """
    Limit version - holds execution limits, timeouts, and budgets.

    Only one version per limit can be ACTIVE at a time.
    """
    __tablename__ = "limit_versions"
    __table_args__ = (
        UniqueConstraint('limit_id', 'version', name='uix_limit_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    limit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('limits.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default=LimitStatus.DRAFT.value,
        nullable=False,
        index=True
    )

    max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_tool_calls: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_wall_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tool_timeout_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    extra_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('limit_versions.id', ondelete='SET NULL'),
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

    limit: Mapped["Limit"] = relationship(
        "Limit",
        back_populates="versions",
        foreign_keys=[limit_id]
    )

    parent_version: Mapped[Optional["LimitVersion"]] = relationship(
        "LimitVersion",
        remote_side=[id],
        foreign_keys=[parent_version_id]
    )

    @property
    def is_editable(self) -> bool:
        return self.status == LimitStatus.DRAFT.value

    @property
    def can_activate(self) -> bool:
        return self.status == LimitStatus.DRAFT.value

    @property
    def can_deactivate(self) -> bool:
        return self.status in (LimitStatus.DRAFT.value, LimitStatus.ACTIVE.value)

    def __repr__(self) -> str:
        return f"<LimitVersion {self.limit_id} v{self.version} ({self.status})>"
