"""
Chat SSE Event Contract — единый источник правды для всех SSE событий чата.

Каждый тип события имеет typed payload schema и factory method для создания
transport-ready dict. Используется в ChatStreamService и chat router.

Event lifecycle (canonical order):
  1. user_message   — user message persisted
  2. chat_title     — auto-generated title (first message only)
  3. status         — pipeline stage updates
  4. agent_selected — triage selected agent
  5. tool_call      — tool invocation started
  6. tool_result    — tool invocation completed
  7. planner_action — planner loop step
  8. delta          — streaming content chunk
  9. confirmation_required — needs user confirmation
  10. waiting_input  — needs additional user input
  11. stop           — run paused (confirmation/input pending)
  12. final          — assistant message persisted, turn complete
  13. cached         — idempotent replay (replaces all above)
  14. error          — error at any point (terminal or recoverable)
  [DONE]            — SSE stream terminator
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatSSEEventType(str, Enum):
    """Canonical chat SSE event types."""
    USER_MESSAGE = "user_message"
    CHAT_TITLE = "chat_title"
    STATUS = "status"
    AGENT_SELECTED = "agent_selected"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLANNER_ACTION = "planner_action"
    DELTA = "delta"
    CONFIRMATION_REQUIRED = "confirmation_required"
    WAITING_INPUT = "waiting_input"
    STOP = "stop"
    FINAL = "final"
    CACHED = "cached"
    ERROR = "error"


# ── Payload schemas ────────────────────────────────────────────────

class UserMessagePayload(BaseModel):
    message_id: str
    created_at: Optional[str] = None


class ChatTitlePayload(BaseModel):
    title: str


class StatusPayload(BaseModel):
    stage: str
    orchestration_envelope: Optional[Dict[str, Any]] = None
    orchestration_state: Optional[Dict[str, Any]] = None


class AgentSelectedPayload(BaseModel):
    agent: Optional[str] = None
    auto: bool = False


class ToolCallPayload(BaseModel):
    tool: Optional[str] = None
    call_id: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


class ToolResultPayload(BaseModel):
    tool: Optional[str] = None
    call_id: Optional[str] = None
    success: Optional[bool] = None
    data: Optional[Any] = None


class PlannerActionPayload(BaseModel):
    iteration: Optional[int] = None
    action_type: Optional[str] = None
    step_type: Optional[str] = None
    agent_slug: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    why: Optional[str] = None
    # Legacy fields kept for backward compatibility with old clients.
    tool_slug: Optional[str] = None
    op: Optional[str] = None
    orchestration_envelope: Optional[Dict[str, Any]] = None
    orchestration_state: Optional[Dict[str, Any]] = None


class DeltaPayload(BaseModel):
    content: str = ""


class ConfirmationRequiredPayload(BaseModel):
    reason: Optional[str] = None
    action: Optional[str] = None


class WaitingInputPayload(BaseModel):
    question: Optional[str] = None
    reason: Optional[str] = None
    orchestration_envelope: Optional[Dict[str, Any]] = None
    orchestration_state: Optional[Dict[str, Any]] = None


class StopPayload(BaseModel):
    reason: Optional[str] = None
    message: Optional[str] = None
    question: Optional[str] = None
    run_id: Optional[str] = None
    orchestration_envelope: Optional[Dict[str, Any]] = None
    orchestration_state: Optional[Dict[str, Any]] = None


class FinalPayload(BaseModel):
    message_id: str
    created_at: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class CachedPayload(BaseModel):
    user_message_id: str
    assistant_message_id: str


class ErrorPayload(BaseModel):
    error: str
    code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ── Payload type mapping ───────────────────────────────────────────

EVENT_PAYLOAD_MAP: Dict[ChatSSEEventType, type] = {
    ChatSSEEventType.USER_MESSAGE: UserMessagePayload,
    ChatSSEEventType.CHAT_TITLE: ChatTitlePayload,
    ChatSSEEventType.STATUS: StatusPayload,
    ChatSSEEventType.AGENT_SELECTED: AgentSelectedPayload,
    ChatSSEEventType.TOOL_CALL: ToolCallPayload,
    ChatSSEEventType.TOOL_RESULT: ToolResultPayload,
    ChatSSEEventType.PLANNER_ACTION: PlannerActionPayload,
    ChatSSEEventType.DELTA: DeltaPayload,
    ChatSSEEventType.CONFIRMATION_REQUIRED: ConfirmationRequiredPayload,
    ChatSSEEventType.WAITING_INPUT: WaitingInputPayload,
    ChatSSEEventType.STOP: StopPayload,
    ChatSSEEventType.FINAL: FinalPayload,
    ChatSSEEventType.CACHED: CachedPayload,
    ChatSSEEventType.ERROR: ErrorPayload,
}


# ── SSE formatting helpers ─────────────────────────────────────────

def format_chat_sse(event_type: ChatSSEEventType, payload: BaseModel) -> str:
    """Format a typed event as SSE text.

    Special handling for delta events to preserve newlines per SSE spec.
    """
    import json

    if event_type == ChatSSEEventType.DELTA:
        content = payload.content if isinstance(payload, DeltaPayload) else ""
        lines = ["event: delta\n"]
        for line in content.splitlines():
            lines.append(f"data: {line}\n")
        if content.endswith("\n"):
            lines.append("data:\n")
        lines.append("\n")
        return "".join(lines)

    data = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event_type.value}\ndata: {data}\n\n"


def format_chat_sse_done() -> str:
    """SSE stream terminator."""
    return "event: done\ndata: [DONE]\n\n"
