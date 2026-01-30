"""
PermissionSet model - RBAC permissions for tool instances
"""
import uuid
from datetime import datetime
from typing import Optional, Dict
from enum import Enum

from sqlalchemy import String, DateTime, ForeignKey, func, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PermissionScope(str, Enum):
    """Scope level for PermissionSet"""
    DEFAULT = "default"
    TENANT = "tenant"
    USER = "user"


class PermissionValue(str, Enum):
    """Permission value for instance access"""
    ALLOWED = "allowed"
    DENIED = "denied"
    UNDEFINED = "undefined"  # Only for tenant/user scope, inherits from parent


class PermissionSet(Base):
    """
    RBAC permissions for tool instances.
    
    Hierarchy: default → tenant → user
    Resolution priority: user > tenant > default
    
    Resolution logic:
    1. Check user level - if explicit allowed/denied, use it
    2. If undefined at user level - check tenant level
    3. If undefined at tenant level - check default level
    4. If not specified anywhere - denied by default
    
    Default scope can only have 'allowed' or 'denied' (no 'undefined').
    Tenant/User scope can have 'allowed', 'denied', or 'undefined'.
    
    instance_permissions format:
    {
        "jira-prod": "allowed",
        "jira-staging": "denied",
        "rag-main": "undefined"  # inherits from parent scope
    }
    """
    __tablename__ = "permission_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    # Instance permissions: {"instance_slug": "allowed" | "denied" | "undefined"}
    instance_permissions: Mapped[Dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Agent permissions: {"agent_slug": "allowed" | "denied" | "undefined"}
    agent_permissions: Mapped[Dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name="permission_sets_scope_check"
        ),
        CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name="permission_sets_scope_refs_check"
        ),
        UniqueConstraint('scope', 'tenant_id', 'user_id', name='uix_permission_sets_scope'),
    )

    def __repr__(self) -> str:
        return f"<PermissionSet {self.scope} tenant={self.tenant_id} user={self.user_id}>"
