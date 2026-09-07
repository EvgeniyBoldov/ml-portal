"""Persistent state for the strict iterative runtime."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimePlan(Base):
    __tablename__ = "runtime_plans"
    __table_args__ = (CheckConstraint("status IN ('draft', 'active', 'waiting_input', 'completed', 'failed', 'cancelled')", name="ck_runtime_plan_status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    root_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    last_failure: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class RuntimePlanIteration(Base):
    __tablename__ = "runtime_plan_iterations"
    __table_args__ = (
        UniqueConstraint("plan_id", "sequence", name="uq_runtime_plan_iteration_sequence"),
        Index("ix_runtime_plan_iteration_active", "plan_id", "status"),
        CheckConstraint("terminal IN ('planner', 'synthesis')", name="ck_runtime_iteration_terminal"),
        CheckConstraint("status IN ('active', 'closed')", name="ck_runtime_iteration_status"),
        CheckConstraint("checkpoint_status IN ('idle', 'planner_running', 'synthesis_running', 'completed')", name="ck_runtime_iteration_checkpoint_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    terminal: Mapped[str] = mapped_column(String(32), nullable=False)
    synthesis_brief: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    proposal: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    checkpoint_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    checkpoint_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimePlanTask(Base):
    __tablename__ = "runtime_plan_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "task_id", name="uq_runtime_plan_task_id"),
        Index("ix_runtime_plan_tasks_ready", "iteration_id", "status"),
        CheckConstraint("status IN ('pending', 'running', 'waiting_retry', 'waiting_confirmation', 'completed', 'needs_dependency', 'unfulfillable', 'failed', 'blocked', 'cancelled')", name="ck_runtime_task_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    iteration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_iterations.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_order: Mapped[int] = mapped_column(Integer, nullable=False)
    intent: Mapped[str] = mapped_column(String(512), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    executor: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expected_outputs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    freshness_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="allow_memory")
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class RuntimeTaskDependency(Base):
    __tablename__ = "runtime_task_dependencies"
    __table_args__ = (UniqueConstraint("task_row_id", "depends_on_task_id", name="uq_runtime_task_dependency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[str] = mapped_column(String(255), nullable=False)


class RuntimeTaskNeed(Base):
    __tablename__ = "runtime_task_needs"
    __table_args__ = (UniqueConstraint("task_row_id", "need_ref", name="uq_runtime_task_need"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False)
    need_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    need_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    context: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    required: Mapped[bool] = mapped_column(nullable=False, default=True)


class RuntimeNeedBinding(Base):
    __tablename__ = "runtime_need_bindings"
    __table_args__ = (UniqueConstraint("plan_id", "consumer_task_id", "consumer_input_key", name="uq_runtime_need_binding_input"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    need_task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    need_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    producer_task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    output_key: Mapped[str] = mapped_column(String(255), nullable=False)
    consumer_task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    consumer_input_key: Mapped[str] = mapped_column(String(255), nullable=False)


class RuntimeTaskResolution(Base):
    __tablename__ = "runtime_task_resolutions"
    __table_args__ = (UniqueConstraint("iteration_id", "task_id", name="uq_runtime_task_resolution"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    iteration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_iterations.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    output_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    replacement_task_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeTaskAttempt(Base):
    __tablename__ = "runtime_task_attempts"
    __table_args__ = (UniqueConstraint("task_row_id", "attempt_number", name="uq_runtime_task_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    execution_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    agent_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimePause(Base):
    __tablename__ = "runtime_pauses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    operation_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
