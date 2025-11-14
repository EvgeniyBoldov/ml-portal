"""
Chat and chat messages models
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from .base import Base

class Chats(Base):
    """Chats table model"""
    __tablename__ = "chats"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[List[str] | None] = mapped_column(ARRAY(String), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    messages = relationship("ChatMessages", back_populates="chat", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_chats_tenant_id", "tenant_id"),
        Index("ix_chats_tenant_created", "tenant_id", "created_at"),
        Index("ix_chats_tenant_owner", "tenant_id", "owner_id"),
        Index("ix_chats_tenant_name", "tenant_id", "name"),
    )

class ChatMessages(Base):
    """
    Chat messages table model
    
    Content structure examples:
    - text: {"type": "text", "text": "Hello"}
    - tool_call: {"type": "tool_call", "tool": "search", "args": {...}, "result": {...}}
    - citation: {"type": "citation", "text": "...", "sources": [{...}]}
    """
    __tablename__ = "chatmessages"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(SQLEnum('system', 'user', 'assistant', 'tool', name='chat_role_enum', create_type=False), nullable=False)
    content: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="text")  # text, tool_call, citation
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    meta: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    chat = relationship("Chats", back_populates="messages")
    
    __table_args__ = (
        Index("ix_chatmessages_chat_id_created_at", "chat_id", "created_at"),
        Index("ix_chatmessages_tenant_id", "tenant_id"),
        Index("ix_chatmessages_tenant_created", "tenant_id", "created_at"),
        Index("ix_chatmessages_tenant_chat", "tenant_id", "chat_id"),
    )

