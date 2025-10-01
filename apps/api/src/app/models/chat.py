from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, Integer, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import uuid

ChatRoleEnum = Enum("system", "user", "assistant", "tool", name="chat_role_enum", create_constraint=True)

class Chats(Base):
    __tablename__ = "chats"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[List["ChatMessages"]] = relationship(back_populates="chat", cascade="all, delete-orphan")
    
    # Composite indexes for multi-tenant queries
    __table_args__ = (
        Index("ix_chats_tenant_created", "tenant_id", "created_at"),
        Index("ix_chats_tenant_owner", "tenant_id", "owner_id"),
        Index("ix_chats_tenant_name", "tenant_id", "name"),
    )

class ChatMessages(Base):
    __tablename__ = "chatmessages"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(ChatRoleEnum, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    chat: Mapped["Chats"] = relationship(back_populates="messages")
    
    # Composite indexes for multi-tenant queries and JSONB search
    __table_args__ = (
        Index("ix_chatmessages_tenant_created", "tenant_id", "created_at"),
        Index("ix_chatmessages_tenant_chat", "tenant_id", "chat_id"),
        Index("ix_chatmessages_content_gin", "content", postgresql_using="gin"),
        Index("ix_chatmessages_meta_gin", "meta", postgresql_using="gin"),
    )
