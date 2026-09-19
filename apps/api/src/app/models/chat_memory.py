"""Typed, chat-local working context with traceable provenance."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ChatMemoryItem(Base):
    """A materialized context item, never a replacement for its source turn."""

    __tablename__ = "chat_memory_items"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('scope', 'term_binding', 'artifact_ref', 'decision', 'open_question', 'chat_fact', 'summary', 'task_result_ref')",
            name="ck_chat_memory_items_kind",
        ),
        CheckConstraint("status IN ('active', 'superseded', 'closed', 'expired')", name="ck_chat_memory_items_status"),
        Index("ix_chat_memory_items_chat_active", "chat_id", "status", "updated_at"),
        Index("ix_chat_memory_items_branch_active", "sandbox_branch_id", "status", "updated_at"),
        Index("ix_chat_memory_items_source_turn", "source_turn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    # A sandbox chat is shared by its session, so branch identity is part of
    # the context key. Ordinary chats keep this NULL.
    sandbox_branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sandbox_branches.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="'{}'::jsonb")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0, server_default="1.0")
    source_turn_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_turns.id", ondelete="SET NULL"), nullable=True)
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("chatmessages.id", ondelete="SET NULL"), nullable=True)
    source_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
