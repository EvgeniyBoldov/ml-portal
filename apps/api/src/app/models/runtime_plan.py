"""Persistent execution graph for Runtime V3."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimePlan(Base):
    __tablename__ = "runtime_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    root_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answer_brief: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_failure: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class RuntimePlanTask(Base):
    __tablename__ = "runtime_plan_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "task_id", name="uq_runtime_plan_task_id"),
        Index("ix_runtime_plan_tasks_ready", "plan_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent: Mapped[str] = mapped_column(String(512), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    executor: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expected_outputs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    on_success: Mapped[str] = mapped_column(String(32), nullable=False, default="continue")
    checkpoint: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class RuntimeTaskDependency(Base):
    __tablename__ = "runtime_task_dependencies"
    __table_args__ = (UniqueConstraint("plan_id", "task_id", "depends_on_task_id", name="uq_runtime_task_dependency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    depends_on_task_id: Mapped[str] = mapped_column(String(255), nullable=False)


class RuntimeTaskNeed(Base):
    __tablename__ = "runtime_task_needs"
    __table_args__ = (UniqueConstraint("task_row_id", "need_key", name="uq_runtime_task_need"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False)
    need_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="data")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    need_metadata: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    resolved_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    resolver_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class RuntimePlanRevision(Base):
    __tablename__ = "runtime_plan_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    patch: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    planner_invocation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class RuntimeTaskAttempt(Base):
    __tablename__ = "runtime_task_attempts"
    __table_args__ = (UniqueConstraint("task_row_id", "attempt_number", name="uq_runtime_task_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    error: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    agent_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
