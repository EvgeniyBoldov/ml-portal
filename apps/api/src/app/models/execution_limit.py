from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExecutionLimitScope:
    PLATFORM = "platform"
    AGENT = "agent"
    ORCHESTRATOR_ROLE = "orchestrator_role"


class ExecutionLimit(Base):
    __tablename__ = "execution_limits"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", name="uq_execution_limits_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # For platform scope uses literal "global".
    scope_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    llm_input_tokens_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_output_tokens_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_context_window_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    runtime_steps_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_tool_calls_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_retries_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_wall_time_ms_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_tokens_total_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

