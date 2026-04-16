"""
Plan model for storing execution plans with pause/resume support.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import String, DateTime, Integer, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlanStatus(str, Enum):
    """Plan execution status."""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class Plan(Base):
    """
    Execution plan for agent runs with pause/resume support.
    
    Stores structured plans created by SystemLLMRole.PLANNER
    and tracks execution progress for resume functionality.
    """
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # === Relationships ===
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Associated agent run (optional)"
    )
    
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Associated chat session (optional)"
    )
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant ID for multi-tenancy"
    )
    
    # === LLM Trace Linkage ===
    planner_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Link to system LLM trace that created this plan"
    )
    
    planner_input: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB(astext_type=String),
        nullable=True,
        comment="Snapshot of PlannerInput at plan creation"
    )
    
    goal_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Where the goal came from: user_message|triage_goal|resume"
    )
    
    # === Plan Data ===
    plan_data: Mapped[dict] = mapped_column(
        JSONB(astext_type=String),
        nullable=False,
        comment="Plan structure with steps and metadata"
    )
    
    # === Execution State ===
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("status IN ('draft', 'active', 'completed', 'failed', 'paused')", name="check_plan_status"),
        nullable=False,
        default=PlanStatus.DRAFT.value,
        index=True,
        comment="Plan status: draft | active | completed | failed | paused"
    )
    
    current_step: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint('current_step >= 0', name="check_current_step_non_negative"),
        nullable=False,
        default=0,
        comment="Current step index for resume functionality"
    )
    
    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
        comment="Plan creation timestamp"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Plan last update timestamp"
    )
    
    def __repr__(self) -> str:
        return f"<Plan {self.id} status={self.status} steps={len(self.plan_data.get('steps', []))}>"
    
    @property
    def steps(self) -> list:
        """Get steps from plan_data."""
        return self.plan_data.get("steps", [])
    
    @property
    def current_step_data(self) -> Optional[dict]:
        """Get current step data if available."""
        steps = self.steps
        if 0 <= self.current_step < len(steps):
            return steps[self.current_step]
        return None
    
    @property
    def is_completed(self) -> bool:
        """Check if plan execution is completed."""
        return self.status == PlanStatus.COMPLETED.value
    
    @property
    def is_paused(self) -> bool:
        """Check if plan execution is paused."""
        return self.status == PlanStatus.PAUSED.value
    
    @property
    def is_active(self) -> bool:
        """Check if plan execution is active."""
        return self.status == PlanStatus.ACTIVE.value
    
    @property
    def progress_percentage(self) -> float:
        """Calculate execution progress as percentage."""
        steps = self.steps
        if not steps:
            return 100.0
        return (self.current_step / len(steps)) * 100
