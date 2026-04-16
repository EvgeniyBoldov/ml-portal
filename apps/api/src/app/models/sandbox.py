"""
Sandbox models — sessions, branches, overrides, snapshots, runs, run steps.

SandboxSession: admin workspace with sliding TTL.
SandboxBranch: branch inside session (git-like lineage).
SandboxBranchOverride: current override key-value state per branch.
SandboxOverrideSnapshot: immutable snapshot of branch overrides at run start.
SandboxOverride: legacy phantom session override (backward compatibility).
SandboxRun: single agent execution within a session/branch/snapshot.
SandboxRunStep: individual step of a run (SSE event persisted).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SandboxSession(Base):
    """
    Admin sandbox workspace with phantom overrides and runs.
    Sliding TTL: expires_at = last_activity_at + ttl_days.
    """
    __tablename__ = "sandbox_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # active | archived
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    ttl_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)

    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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

    # Relationships
    overrides: Mapped[List["SandboxOverride"]] = relationship(
        "SandboxOverride",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SandboxOverride.created_at",
    )
    runs: Mapped[List["SandboxRun"]] = relationship(
        "SandboxRun",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SandboxRun.started_at.desc()",
    )
    branches: Mapped[List["SandboxBranch"]] = relationship(
        "SandboxBranch",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SandboxBranch.created_at",
    )
    snapshots: Mapped[List["SandboxOverrideSnapshot"]] = relationship(
        "SandboxOverrideSnapshot",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SandboxOverrideSnapshot.created_at.desc()",
    )

    __table_args__ = (
        Index("ix_sandbox_sessions_owner_id", "owner_id"),
        Index("ix_sandbox_sessions_status_expires", "status", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<SandboxSession {self.id} name={self.name!r} status={self.status}>"


class SandboxOverride(Base):
    """
    Phantom version override within a sandbox session.
    entity_type: agent_version | tool_release | orchestration | policy | limit | model
    config_snapshot: full config payload (not a diff).
    """
    __tablename__ = "sandbox_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # agent_version | tool_release | orchestration | policy | limit | model
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # ID of the real entity this overrides (null for brand-new phantom)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)

    # Whether this override is the "active" one used for runs
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    config_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
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

    # Relationships
    session: Mapped["SandboxSession"] = relationship(
        "SandboxSession", back_populates="overrides"
    )

    __table_args__ = (
        Index("ix_sandbox_overrides_session_id", "session_id"),
        Index("ix_sandbox_overrides_entity", "session_id", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return f"<SandboxOverride {self.id} type={self.entity_type} label={self.label!r}>"


class SandboxBranch(Base):
    """Branch inside sandbox session with lineage to parent branch/run."""

    __tablename__ = "sandbox_branches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
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

    session: Mapped["SandboxSession"] = relationship("SandboxSession", back_populates="branches")
    overrides: Mapped[List["SandboxBranchOverride"]] = relationship(
        "SandboxBranchOverride",
        back_populates="branch",
        cascade="all, delete-orphan",
        order_by="SandboxBranchOverride.created_at",
    )
    snapshots: Mapped[List["SandboxOverrideSnapshot"]] = relationship(
        "SandboxOverrideSnapshot",
        back_populates="branch",
        cascade="all, delete-orphan",
        order_by="SandboxOverrideSnapshot.created_at.desc()",
    )
    runs: Mapped[List["SandboxRun"]] = relationship(
        "SandboxRun",
        back_populates="branch",
        foreign_keys="SandboxRun.branch_id",
    )

    __table_args__ = (
        Index("ix_sandbox_branches_session_id", "session_id"),
        Index("ix_sandbox_branches_parent_branch_id", "parent_branch_id"),
        Index("ix_sandbox_branches_parent_run_id", "parent_run_id"),
    )


class SandboxBranchOverride(Base):
    """Current branch override key-value state (one key = one value)."""

    __tablename__ = "sandbox_branch_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_branches.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    field_path: Mapped[str] = mapped_column(String(255), nullable=False)
    value_json: Mapped[Dict[str, Any] | List[Any] | str | int | float | bool | None] = mapped_column(JSONB, nullable=True)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False, default="json")
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
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

    branch: Mapped["SandboxBranch"] = relationship("SandboxBranch", back_populates="overrides")

    __table_args__ = (
        Index("ix_sandbox_branch_overrides_branch_id", "branch_id"),
        Index(
            "uq_sandbox_branch_overrides_key",
            "branch_id",
            "entity_type",
            "entity_id",
            "field_path",
            unique=True,
        ),
    )


class SandboxOverrideSnapshot(Base):
    """Immutable snapshot of branch overrides used by run for reproducibility."""

    __tablename__ = "sandbox_override_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_branches.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session: Mapped["SandboxSession"] = relationship("SandboxSession", back_populates="snapshots")
    branch: Mapped["SandboxBranch"] = relationship("SandboxBranch", back_populates="snapshots")
    runs: Mapped[List["SandboxRun"]] = relationship(
        "SandboxRun",
        back_populates="snapshot",
        foreign_keys="SandboxRun.snapshot_id",
    )

    __table_args__ = (
        Index("ix_sandbox_override_snapshots_session_id", "session_id"),
        Index("ix_sandbox_override_snapshots_branch_id", "branch_id"),
        Index("ix_sandbox_override_snapshots_hash", "snapshot_hash"),
    )


class SandboxRun(Base):
    """
    Single agent execution within a sandbox session.
    effective_config: frozen snapshot of merged system + overrides config at run start.
    """
    __tablename__ = "sandbox_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_branches.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_override_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )

    parent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    request_text: Mapped[str] = mapped_column(Text, nullable=False)

    # running | completed | failed | waiting_confirmation
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")

    effective_config: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # Pause state for confirmation flow
    paused_action: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    paused_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    session: Mapped["SandboxSession"] = relationship(
        "SandboxSession", back_populates="runs"
    )
    branch: Mapped["SandboxBranch"] = relationship(
        "SandboxBranch",
        back_populates="runs",
        foreign_keys=[branch_id],
    )
    snapshot: Mapped["SandboxOverrideSnapshot"] = relationship(
        "SandboxOverrideSnapshot",
        back_populates="runs",
        foreign_keys=[snapshot_id],
    )
    steps: Mapped[List["SandboxRunStep"]] = relationship(
        "SandboxRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SandboxRunStep.order_num",
    )

    __table_args__ = (
        Index("ix_sandbox_runs_session_id", "session_id"),
        Index("ix_sandbox_runs_branch_id", "branch_id"),
        Index("ix_sandbox_runs_snapshot_id", "snapshot_id"),
    )

    def __repr__(self) -> str:
        return f"<SandboxRun {self.id} status={self.status}>"


class SandboxRunStep(Base):
    """
    Individual step persisted from SSE stream during a sandbox run.
    """
    __tablename__ = "sandbox_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # status | thinking | routing | tool_call | tool_result | delta | final | error | confirmation_required
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)

    step_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    order_num: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    run: Mapped["SandboxRun"] = relationship("SandboxRun", back_populates="steps")

    __table_args__ = (
        Index("ix_sandbox_run_steps_run_id", "run_id"),
    )

    def __repr__(self) -> str:
        return f"<SandboxRunStep {self.order_num} type={self.step_type}>"
