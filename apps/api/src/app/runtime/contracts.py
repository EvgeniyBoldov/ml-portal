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
    """Safe, opaque file reference used by every runtime participant."""

    artifact_id: str = Field(..., min_length=1)
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
