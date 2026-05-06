"""
User model for authentication and authorization
"""
from __future__ import annotations
from sqlalchemy import String, Boolean, Text, DateTime, Index, func, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid

from .base import Base

class Users(Base):
    """Users table model"""
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # NULL for LDAP users
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="reader")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    require_password_change: Mapped[bool | None] = mapped_column(Boolean, nullable=True, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # LDAP fields
    auth_provider: Mapped[str] = mapped_column(String(16), nullable=False, server_default="local")
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)  # LDAP DN or objectGUID
    ldap_groups: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # PostgreSQL array
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # displayName from LDAP
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    __table_args__ = (
        Index("ix_users_login", "login", unique=True),
        Index("ix_users_auth_provider_external_id", "auth_provider", "external_id", unique=True, postgresql_where="external_id IS NOT NULL"),
    )

