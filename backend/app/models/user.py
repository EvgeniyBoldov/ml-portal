from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

RolesEnum = Enum("admin", "editor", "reader", name="role_enum", create_constraint=True)

class Users(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    login: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(RolesEnum, nullable=False, default="reader")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")

    # relationships
    refresh_tokens: Mapped[List["UserRefreshTokens"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    pat_tokens: Mapped[List["UserTokens"]] = relationship(back_populates="user", cascade="all, delete-orphan")

import uuid

class UserTokens(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["Users"] = relationship(back_populates="pat_tokens", primaryjoin="Users.id==foreign(UserTokens.user_id)")

class UserRefreshTokens(Base):
    __table_args__ = (
        UniqueConstraint("refresh_hash", name="uq_user_refresh_tokens_refresh_hash"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    refresh_hash: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta: Mapped[Optional[dict]] = mapped_column(Text, nullable=True)  # store JSON as text (or JSONB via sqlalchemy.dialects)

    user: Mapped["Users"] = relationship(back_populates="refresh_tokens", primaryjoin="Users.id==foreign(UserRefreshTokens.user_id)")
