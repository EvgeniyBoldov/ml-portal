from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActorExecutionLimitScope:
    """Scopes for the replacement, actor-oriented execution limits model."""

    AGENT_DEFAULT = "agent_default"
    ORCHESTRATOR_DEFAULT = "orchestrator_default"
    AGENT = "agent"
    ORCHESTRATOR_ROLE = "orchestrator_role"


class RuntimeExecutionLimits(Base):
    """One platform-wide guard for graph execution lifecycle."""

    __tablename__ = "runtime_execution_limits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_ref: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default="global")
    wall_time_ms_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_parallel_tasks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_task_executions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )


class ActorExecutionLimit(Base):
    """Sparse defaults and overrides for one class of runtime actor."""

    __tablename__ = "actor_execution_limits"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref", name="uq_actor_execution_limits_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    llm_calls_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tool_calls_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wall_time_ms_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False,
    )
