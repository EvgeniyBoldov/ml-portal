"""
RBAC models v2 - granular resource-level access control.

Architecture:
- RbacPolicy (набор правил) — named collection of rules, referenced by platform/tenant/user
- RbacRule (правило) — single rule: level + resource_type + resource_id → allow/deny

Levels: platform → tenant → user (resolution priority: user > tenant > platform)
Resource types: agent, toolgroup, tool, instance
Effects: allow, deny
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum

from sqlalchemy import String, DateTime, Text, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RbacLevel(str, Enum):
    """RBAC rule level"""
    PLATFORM = "platform"
    TENANT = "tenant"
    USER = "user"


class ResourceType(str, Enum):
    """RBAC resource type"""
    AGENT = "agent"
    TOOLGROUP = "toolgroup"
    TOOL = "tool"
    INSTANCE = "instance"


class RbacEffect(str, Enum):
    """RBAC rule effect"""
    ALLOW = "allow"
    DENY = "deny"


class RbacPolicy(Base):
    """
    Named set of RBAC rules.
    
    Referenced by platform_settings, tenants, or users.
    Each policy contains multiple rules that define access to resources.
    """
    __tablename__ = "rbac_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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

    rules: Mapped[List["RbacRule"]] = relationship(
        "RbacRule",
        back_populates="rbac_policy",
        cascade="all, delete-orphan",
        order_by="RbacRule.created_at"
    )

    def __repr__(self):
        return f"<RbacPolicy {self.slug}>"


class RbacRule(Base):
    """
    Single RBAC rule — defines access to a specific resource.
    
    level: platform | tenant | user
    level_id: NULL for platform, tenant_id or user_id otherwise
    resource_type: agent | toolgroup | tool | instance
    resource_id: UUID of the resource
    effect: allow | deny
    
    Invariants:
    - UNIQUE(rbac_policy_id, level, level_id, resource_type, resource_id)
    - platform level → level_id IS NULL
    - tenant/user level → level_id IS NOT NULL
    """
    __tablename__ = "rbac_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    rbac_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rbac_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    level: Mapped[str] = mapped_column(String(20), nullable=False)

    level_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    effect: Mapped[str] = mapped_column(String(10), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    rbac_policy: Mapped["RbacPolicy"] = relationship(
        "RbacPolicy",
        back_populates="rules",
        foreign_keys=[rbac_policy_id]
    )

    __table_args__ = (
        UniqueConstraint(
            'rbac_policy_id', 'level', 'level_id', 'resource_type', 'resource_id',
            name='uq_rbac_rule_unique'
        ),
        CheckConstraint(
            "level IN ('platform', 'tenant', 'user')",
            name="ck_rbac_rule_level"
        ),
        CheckConstraint(
            "resource_type IN ('agent', 'toolgroup', 'tool', 'instance')",
            name="ck_rbac_rule_resource_type"
        ),
        CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_rbac_rule_effect"
        ),
        CheckConstraint(
            """
            (level = 'platform' AND level_id IS NULL) OR
            (level IN ('tenant', 'user') AND level_id IS NOT NULL)
            """,
            name="ck_rbac_rule_level_id"
        ),
        Index('ix_rbac_rule_resource', 'resource_type', 'resource_id', 'effect'),
        Index('ix_rbac_rule_level', 'level', 'level_id'),
        Index('ix_rbac_rule_lookup', 'level', 'level_id', 'resource_type', 'resource_id'),
    )

    def __repr__(self):
        return f"<RbacRule {self.level}:{self.resource_type}:{self.resource_id}={self.effect}>"
