"""Revision head for a materialized chat-context scope."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ChatContextHead(Base):
    """The CAS boundary for one chat (and, optionally, one sandbox branch)."""

    __tablename__ = "chat_context_heads"
    __table_args__ = (
        Index("uq_chat_context_heads_chat_root", "chat_id", unique=True,
              postgresql_where=text("sandbox_branch_id IS NULL")),
        Index("uq_chat_context_heads_chat_branch", "chat_id", "sandbox_branch_id", unique=True,
              postgresql_where=text("sandbox_branch_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    sandbox_branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sandbox_branches.id", ondelete="CASCADE"), nullable=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_through_turn_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_turns.id", ondelete="SET NULL"), nullable=True,
    )
    updated_through_turn_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
