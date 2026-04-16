from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatTurn(Base):
    """Persistent lifecycle record for a single chat turn."""

    __tablename__ = "chat_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chatmessages.id", ondelete="SET NULL"),
        nullable=True,
    )
    assistant_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chatmessages.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="started", server_default="started")
    pause_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paused_action: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    paused_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_chat_turns_chat_id_started_at", "chat_id", "started_at"),
        Index("ix_chat_turns_tenant_id", "tenant_id"),
        Index("ix_chat_turns_user_id", "user_id"),
        Index("ix_chat_turns_idempotency_key", "idempotency_key"),
        Index("ix_chat_turns_request_hash", "request_hash"),
        Index("ix_chat_turns_pause_status", "pause_status"),
    )

    def __repr__(self) -> str:
        return f"<ChatTurn {self.id} chat={self.chat_id} status={self.status}>"
