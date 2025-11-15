"""
Event Outbox model for reliable SSE event delivery
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, BigInteger, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from app.models.base import Base


class EventOutbox(Base):
    """Reliable event delivery via outbox pattern"""
    __tablename__ = "events_outbox"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        comment='Sequential number for ordering (BIGSERIAL)'
    )
    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='rag.status|rag.embed.progress|rag.tags.updated|rag.deleted'
    )
    payload_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment='Event payload'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment='Timestamp when event was delivered to at least one SSE client'
    )
    
    __table_args__ = (
        Index('ix_events_outbox_seq', 'seq'),
        Index('ix_events_outbox_type', 'type'),
        Index('ix_events_outbox_delivered_at', 'delivered_at'),
        Index('ix_events_outbox_created_at', 'created_at'),
        Index('ix_events_outbox_delivered_created', 'delivered_at', 'created_at'),
    )
