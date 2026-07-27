"""Persisted budget and observation records for the canonical runtime."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeBudgetCounter(Base):
    __tablename__ = "runtime_budget_counters"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "metric", name="uq_runtime_budget_counter"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class RuntimeBudgetEntry(Base):
    __tablename__ = "runtime_budget_entries"
    __table_args__ = (Index("ix_runtime_budget_entry_owner", "owner_type", "owner_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    before_value: Mapped[int] = mapped_column(Integer, nullable=False)
    after_value: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class RuntimeExecutionEvent(Base):
    __tablename__ = "runtime_execution_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_runtime_execution_event_run_sequence"),
        Index("ix_runtime_event_run_sequence", "run_id", "sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    parent_entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    parent_entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    trigger: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    caused_by_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    logging_level: Mapped[str] = mapped_column(String(10), nullable=False, default="brief")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class RuntimeEventSequence(Base):
    __tablename__ = "runtime_event_sequences"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    next_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RuntimePlannerInvocation(Base):
    __tablename__ = "runtime_planner_invocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    orchestrator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    trigger: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    revision_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revision_after: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
