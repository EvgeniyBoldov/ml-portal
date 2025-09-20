# app/models/user.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from sqlalchemy import String, Boolean, Text, DateTime, UniqueConstraint, ForeignKey, Index, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

class Users(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'editor', 'reader', 'user')", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="reader")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    require_password_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    refresh_tokens: Mapped[List["UserRefreshTokens"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    pat_tokens: Mapped[List["UserTokens"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[List["PasswordResetTokens"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[List["AuditLogs"]] = relationship(
        back_populates="actor_user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class UserTokens(Base):
    __tablename__ = "user_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scopes: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["Users"] = relationship(back_populates="pat_tokens")

class UserRefreshTokens(Base):
    __tablename__ = "user_refresh_tokens"

    __table_args__ = (
        UniqueConstraint("refresh_hash", name="uq_user_refresh_tokens_refresh_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_hash: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON encoded as text

    user: Mapped["Users"] = relationship(back_populates="refresh_tokens")


class PasswordResetTokens(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")

    user: Mapped["Users"] = relationship(back_populates="password_reset_tokens")


class AuditLogs(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()", index=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    object_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 support
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    actor_user: Mapped[Optional["Users"]] = relationship(back_populates="audit_logs")