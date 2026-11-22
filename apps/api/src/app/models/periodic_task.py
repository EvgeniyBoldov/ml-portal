from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PeriodicTask(Base):
    __tablename__ = "periodic_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    task_path: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_schedule: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_orphaned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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


class PeriodicTaskRun(Base):
    __tablename__ = "periodic_task_runs"
    __table_args__ = (Index("ix_periodic_task_runs_latest", "task_id", "created_at", "id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periodic_tasks.id", ondelete="CASCADE"), nullable=False,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    result: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    result_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
