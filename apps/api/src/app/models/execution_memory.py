"""ExecutionMemory model for orchestration state and planner memory."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExecutionMemory(Base):
    """Stores planner/orchestration memory for a single execution run."""

    __tablename__ = "execution_memories"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    chat_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dialogue_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    current_phase_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    current_agent_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    step_history: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    agent_results: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    facts: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    open_questions: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    loop_signatures: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    memory_state: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        default=dict,
    )
    run_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    final_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
