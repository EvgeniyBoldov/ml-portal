"""
Policy model - execution limits and constraints for agents.

Architecture:
- Policy (container) - holds metadata: slug, name, description
- PolicyVersion - holds versioned data: limits, timeouts, budgets
- recommended_version_id - points to the version that should be used by default

Version statuses:
- draft: can be edited, can be activated
- active: used by agents (only one per policy)
- inactive: blocked, cannot be used even via admin
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PolicyStatus(str, Enum):
    """Policy version status"""
    DRAFT = "draft"        # Can be edited, can be activated
    ACTIVE = "active"      # Used by agents (only one per policy)
    INACTIVE = "inactive"  # Blocked, cannot be used


class Policy(Base):
    """
    Policy container - holds metadata for execution policy.
    
    A policy is identified by a unique slug and contains:
    - name: Display name
    - description: Documentation
    - recommended_version_id: Points to the version to use
    
    Each policy can have multiple versions (PolicyVersion).
    """
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Reference to recommended version
    recommended_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('policy_versions.id', ondelete='SET NULL', use_alter=True),
        nullable=True,
        index=True
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # Relationship to versions
    versions: Mapped[List["PolicyVersion"]] = relationship(
        "PolicyVersion",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="desc(PolicyVersion.version)",
        foreign_keys="PolicyVersion.policy_id"
    )
    
    # Relationship to recommended version
    recommended_version: Mapped[Optional["PolicyVersion"]] = relationship(
        "PolicyVersion",
        foreign_keys=[recommended_version_id],
        post_update=True
    )

    def __repr__(self) -> str:
        return f"<Policy {self.slug}>"


class PolicyVersion(Base):
    """
    Policy version - holds limits, timeouts, and budgets.
    
    Each version belongs to a Policy and contains:
    - version: Sequential version number (1, 2, 3...)
    - status: draft, active, or inactive
    - Execution limits and budgets
    
    Only one version per policy can be ACTIVE at a time.
    """
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint('policy_id', 'version', name='uix_policy_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Foreign key to policy container
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('policies.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Sequential version number
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Version status: draft (editable), active (in use), inactive (blocked)
    status: Mapped[str] = mapped_column(
        String(20), 
        default=PolicyStatus.DRAFT.value, 
        nullable=False,
        index=True
    )
    
    # Execution limits
    max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_tool_calls: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_wall_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Tool execution
    tool_timeout_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Budget limits
    budget_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    budget_cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Extended configuration (for future fields)
    extra_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Reference to parent version (for tracking version history)
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('policy_versions.id', ondelete='SET NULL'),
        nullable=True
    )
    
    # Notes about this version (what changed)
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
    
    # Relationships
    policy: Mapped["Policy"] = relationship(
        "Policy", 
        back_populates="versions",
        foreign_keys=[policy_id]
    )
    
    parent_version: Mapped[Optional["PolicyVersion"]] = relationship(
        "PolicyVersion", 
        remote_side=[id],
        foreign_keys=[parent_version_id]
    )

    @property
    def is_editable(self) -> bool:
        """Only draft versions can be edited"""
        return self.status == PolicyStatus.DRAFT.value
    
    @property
    def can_activate(self) -> bool:
        """Only draft versions can be activated"""
        return self.status == PolicyStatus.DRAFT.value
    
    @property
    def can_deactivate(self) -> bool:
        """Draft and active versions can be deactivated"""
        return self.status in (PolicyStatus.DRAFT.value, PolicyStatus.ACTIVE.value)

    def __repr__(self) -> str:
        return f"<PolicyVersion {self.policy_id} v{self.version} ({self.status})>"
