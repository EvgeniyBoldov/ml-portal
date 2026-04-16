"""
Credential model v2 - owner-based credentials for ToolInstance.

Owner is exactly one of: user, tenant, or platform.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthType(str, Enum):
    """Тип авторизации"""
    TOKEN = "token"
    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "api_key"


class Credential(Base):
    """
    Credential v2 - owner-based credentials for ToolInstance.
    
    Exactly one owner must be set:
    - owner_user_id: personal user credentials
    - owner_tenant_id: shared tenant credentials
    - owner_platform=True: platform-wide credentials
    
    Resolution priority depends on operation/tool credential scope and
    compatibility strategies for legacy bindings.
    """
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_instances.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    
    # Owner (exactly one must be set)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    owner_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    owner_platform: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            """
            (owner_platform::int +
             (owner_user_id IS NOT NULL)::int +
             (owner_tenant_id IS NOT NULL)::int) = 1
            """,
            name="ck_credential_single_owner"
        ),
        CheckConstraint(
            "auth_type IN ('token', 'basic', 'oauth', 'api_key')",
            name="ck_credential_auth_type"
        ),
        Index("ix_credential_user_lookup", "owner_user_id", "instance_id",
              postgresql_where="is_active = true"),
        Index("ix_credential_tenant_lookup", "owner_tenant_id", "instance_id",
              postgresql_where="is_active = true"),
        Index("ix_credential_platform_lookup", "owner_platform", "instance_id",
              postgresql_where="is_active = true"),
    )

    def __repr__(self) -> str:
        owner = "platform" if self.owner_platform else (
            f"user:{self.owner_user_id}" if self.owner_user_id else f"tenant:{self.owner_tenant_id}"
        )
        return f"<Credential {self.id} ({owner}/{self.auth_type})>"
