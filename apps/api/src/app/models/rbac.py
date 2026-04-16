"""
RBAC models v3 - flat resource-level access control.

Architecture (v3 — flattened):
- RbacRule (правило) — single rule with direct owner binding
  Owner is exactly one of: user, tenant, or platform.
  resource_type + resource_id → allow/deny

Levels: platform → tenant → user (resolution priority: user > tenant > platform)
Resource types: agent, tool, instance, collection, operation
Effects: allow, deny

No more RbacPolicy container — rules are bound directly to owners.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RbacLevel(str, Enum):
    """RBAC rule level"""
    PLATFORM = "platform"
    TENANT = "tenant"
    USER = "user"


class ResourceType(str, Enum):
    """RBAC resource type"""
    AGENT = "agent"
    TOOL = "tool"
    INSTANCE = "instance"
    COLLECTION = "collection"
    OPERATION = "operation"


class RbacEffect(str, Enum):
    """RBAC rule effect"""
    ALLOW = "allow"
    DENY = "deny"


class RbacRule(Base):
    """
    Single RBAC rule — defines access to a specific resource.
    
    Owner is exactly one of:
    - owner_user_id: personal user rule
    - owner_tenant_id: shared tenant rule
    - owner_platform=True: platform-wide rule
    
    resource_type: agent | tool | instance | collection | operation
    resource_id: UUID of the resource
    effect: allow | deny
    level: platform | tenant | user (for resolution priority)
    
    Resolution priority: user > tenant > platform
    """
    __tablename__ = "rbac_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    level: Mapped[str] = mapped_column(String(20), nullable=False)

    # Owner (exactly one must be set)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    owner_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    owner_platform: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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

    __table_args__ = (
        UniqueConstraint(
            'level', 'owner_user_id', 'owner_tenant_id', 'owner_platform',
            'resource_type', 'resource_id',
            name='uq_rbac_rule_owner_resource'
        ),
        CheckConstraint(
            "level IN ('platform', 'tenant', 'user')",
            name="ck_rbac_rule_level"
        ),
        CheckConstraint(
            "resource_type IN ('agent', 'tool', 'instance', 'collection', 'operation')",
            name="ck_rbac_rule_resource_type"
        ),
        CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_rbac_rule_effect"
        ),
        CheckConstraint(
            """
            (owner_platform::int +
             (owner_user_id IS NOT NULL)::int +
             (owner_tenant_id IS NOT NULL)::int) = 1
            """,
            name="ck_rbac_rule_single_owner"
        ),
        Index('ix_rbac_rule_resource', 'resource_type', 'resource_id', 'effect'),
        Index('ix_rbac_rule_owner_user', 'owner_user_id',
              postgresql_where='owner_user_id IS NOT NULL'),
        Index('ix_rbac_rule_owner_tenant', 'owner_tenant_id',
              postgresql_where='owner_tenant_id IS NOT NULL'),
        Index('ix_rbac_rule_lookup', 'level', 'resource_type', 'resource_id'),
    )

    def __repr__(self):
        owner = "platform" if self.owner_platform else (
            f"user:{self.owner_user_id}" if self.owner_user_id else f"tenant:{self.owner_tenant_id}"
        )
        return f"<RbacRule {owner}:{self.resource_type}:{self.resource_id}={self.effect}>"
