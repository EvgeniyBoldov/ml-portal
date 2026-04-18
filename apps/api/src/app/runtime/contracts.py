"""
Runtime v3 contracts.

Key primitives:
    * PipelineRequest — incoming turn from chat/sandbox
    * TriageDecision  — decision #1: answer | clarify | plan | resume
    * NextStep        — decision #N: call_agent | ask_user | final | abort
    * PipelineStopReason — terminal reasons (waiting_*, completed, failed...)

All shapes are Pydantic models. No dataclasses here — we want JSON round-trip
for persistence into WorkingMemory.memory_state and traces.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Pipeline inputs                                                             #
# --------------------------------------------------------------------------- #


class PipelineRequest(BaseModel):
    """Incoming request to the runtime pipeline. Produced by ChatTurnOrchestrator
    or Sandbox. All ids are strings at this boundary for easy serialization."""

    request_text: str = Field(..., min_length=1)
    chat_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)

    # Full LLM context (system + summary + recent + attachments + current user).
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    # Optional overrides
    agent_slug: Optional[str] = None
    agent_version_id: Optional[str] = None
    model: Optional[str] = None

    # Resume pointer (set by ChatTurnOrchestrator when user answers a paused run)
    resume_run_id: Optional[str] = None

    # Sandbox / continuation metadata (opaque)
    sandbox_overrides: Dict[str, Any] = Field(default_factory=dict)
    continuation_meta: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Triage                                                                      #
# --------------------------------------------------------------------------- #


class TriageIntent(str, Enum):
    FINAL = "final"             # answer directly from triage
    CLARIFY = "clarify"         # ask user for more info before planning
    ORCHESTRATE = "orchestrate" # hand off to planner
    RESUME = "resume"           # continue a paused run (user answered open_question)


class TriageDecision(BaseModel):
    """Output of the Triage stage. Strictly validated."""

    intent: TriageIntent
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    goal: Optional[str] = None                  # normalized objective (set for orchestrate/resume)
    answer: Optional[str] = None                # filled when intent=final
    clarify_prompt: Optional[str] = None        # filled when intent=clarify
    resume_run_id: Optional[UUID] = None        # filled when intent=resume
    agent_hint: Optional[str] = None            # optional preferred agent slug
    reason: Optional[str] = None                # human-readable rationale (for trace)


# --------------------------------------------------------------------------- #
# Planner NextStep                                                            #
# --------------------------------------------------------------------------- #


class NextStepKind(str, Enum):
    CALL_AGENT = "call_agent"   # delegate to a sub-agent (the only way to touch tools)
    ASK_USER = "ask_user"       # pause for user input
    FINAL = "final"             # synthesize and emit final answer
    ABORT = "abort"             # give up (non-recoverable planner failure)


class NextStep(BaseModel):
    """Canonical planner decision. LLM must produce JSON matching this schema."""

    kind: NextStepKind
    rationale: str = Field(..., min_length=1, max_length=2000)

    # --- CALL_AGENT ---
    agent_slug: Optional[str] = None
    agent_input: Dict[str, Any] = Field(default_factory=dict)  # {query, phase_id, ...}

    # --- ASK_USER ---
    question: Optional[str] = None

    # --- FINAL ---
    final_answer: Optional[str] = None

    # --- metadata ---
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False


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
