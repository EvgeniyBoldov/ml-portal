"""
Runtime v3 contracts.

Key primitives:
    * PipelineRequest — incoming turn from chat/sandbox
    * PipelineStopReason — terminal reasons (waiting_*, completed, failed...)
    * RuntimeTurnState — canonical turn state (replaces legacy WorkingMemory)

All shapes are Pydantic models. No dataclasses here — we want JSON round-trip
for persistence into traces and cross-turn memory.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    NORMAL = "normal"
    THINKING = "thinking"


class AttachmentRef(BaseModel):
    id: str = Field(..., min_length=1)
    artifact_id: Optional[str] = None
    file_id: str = Field(..., min_length=1)
    storage_uri: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    file_ext: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    status: Optional[str] = None


class AttachmentContext(BaseModel):
    ref: AttachmentRef
    snippet: str = ""
    snippet_status: Literal["ready", "truncated", "unreadable", "missing"] = "missing"
    readable: bool = False
    truncated: bool = False


# --------------------------------------------------------------------------- #
# Pipeline inputs                                                             #
# --------------------------------------------------------------------------- #


class PipelineRequest(BaseModel):
    """Incoming request to the runtime pipeline. Produced by ChatTurnOrchestrator
    or Sandbox. All ids are strings at this boundary for easy serialization."""

    request_text: str = Field(..., min_length=1)
    # Canonical runtime identity shared by plan, events, SSE and timeline.
    # Entry points create it; the pipeline never generates a second root id.
    runtime_run_id: Optional[str] = None
    # chat_id is None for sandbox runs that have no persistent chat binding.
    chat_id: Optional[str] = None
    user_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)

    # Full LLM context (system + summary + recent + attachments + current user).
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    attachments: List[AttachmentContext] = Field(default_factory=list)

    # Optional overrides
    agent_slug: Optional[str] = None
    agent_version_id: Optional[str] = None
    model: Optional[str] = None

    # Resume pointer (set by ChatTurnOrchestrator when user answers a paused run)
    resume_run_id: Optional[str] = None

    # Sandbox / continuation metadata (opaque)
    sandbox_overrides: Dict[str, Any] = Field(default_factory=dict)
    continuation_meta: Dict[str, Any] = Field(default_factory=dict)
    confirmation_tokens: List[str] = Field(default_factory=list)
    await_background_tail: bool = True
    execution_mode: ExecutionMode = ExecutionMode.NORMAL


# --------------------------------------------------------------------------- #
# Stop reasons                                                                #
# --------------------------------------------------------------------------- #


class PipelineStopReason(str, Enum):
    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    FAILED = "failed"
    LOOP_DETECTED = "loop_detected"
    BUDGET_EXCEEDED = "budget_exceeded"
    MAX_ITERS = "max_iters"
    ABORTED = "aborted"


# --------------------------------------------------------------------------- #
# Agent answer contract (needs-aware)                                         #
# --------------------------------------------------------------------------- #


class AgentAnswerStatus(str, Enum):
    COMPLETE = "complete"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"


class NeedSpec(BaseModel):
    """A machine-routable need declared by an agent."""
    ref: str = Field(..., description="Local id of the need within the agent result (e.g. 'need-lun-uuid')")
    kind: Literal["data", "artifact", "decision"] = "data"
    key: str = Field(..., description="Machine key for planner routing (e.g. 'lun_uuid')")
    description: str = Field(..., min_length=1, description="Human-readable: why this is needed")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional routing context")
    resolved_value: Optional[Any] = Field(default=None, description="Filled by planner after resolution")
    resolved_by: Optional[str] = Field(default=None, description="Agent slug that resolved this need")
    resolved_at_iteration: Optional[int] = Field(default=None)


class TaskJournalNeed(BaseModel):
    """Need as recorded in the task journal (immutable once resolved)."""
    ref: str
    key: str
    description: str
    kind: str = "data"
    resolved_value: Optional[Any] = None
    resolved_by: Optional[str] = None
    resolved_at_iteration: Optional[int] = None
    status: Literal["pending", "resolved", "deferred"] = "pending"


class TaskJournalEntry(BaseModel):
    """One task in the accumulating plan, tracked across iterations."""
    task_id: str = Field(..., description="Stable id of the plan item")
    title: str = ""
    assigned_agent: Optional[str] = None
    status: Literal["pending", "in_progress", "paused_need", "resolved", "deferred", "failed"] = "pending"
    needs: List[TaskJournalNeed] = Field(default_factory=list)
    attempts: int = 0
    max_pauses: int = 3
    summary: str = ""
    origin_agent: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    iteration_started: Optional[int] = None
    iteration_resolved: Optional[int] = None
