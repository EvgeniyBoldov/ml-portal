"""
Runtime v3 contracts.

Key primitives:
    * PipelineRequest — incoming turn from chat/sandbox
    * NextStep        — planner decision: call_agent | ask_user | clarify | final | abort
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


# --------------------------------------------------------------------------- #
# Pipeline inputs                                                             #
# --------------------------------------------------------------------------- #


class PipelineRequest(BaseModel):
    """Incoming request to the runtime pipeline. Produced by ChatTurnOrchestrator
    or Sandbox. All ids are strings at this boundary for easy serialization."""

    request_text: str = Field(..., min_length=1)
    # chat_id is None for sandbox runs that have no persistent chat binding.
    chat_id: Optional[str] = None
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
    confirmation_tokens: List[str] = Field(default_factory=list)
    await_background_tail: bool = True
    execution_mode: ExecutionMode = ExecutionMode.NORMAL


# --------------------------------------------------------------------------- #
# Planner NextStep                                                            #
# --------------------------------------------------------------------------- #


class NextStepKind(str, Enum):
    # --- non-terminal ---
    CALL_AGENT = "call_agent"   # delegate to a sub-agent (the only way to touch tools)
    # --- terminal ---
    ASK_USER = "ask_user"       # pause for user input (legacy name for CLARIFY)
    CLARIFY = "clarify"         # ask user a focused question — alias-kind with semantically
                                # identical handling to ASK_USER; kept separate so planner
                                # prompts can distinguish "I need a single clarification" from
                                # "I need the user to fill an entire form".
    FINAL = "final"             # synthesize and emit final answer (agent work complete)
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
    # Explicit strategy: how should synthesizer treat this final step?
    #   "synthesize" — run LLM synthesis (default)
    #   "verbatim" — stream final_answer as-is (bypass LLM)
    #   "use_agent_result" — synthesize from single successful agent result
    final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize"

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
