"""Public, typed SSE contract for chat execution."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.chat_lifecycle import ChatExecutionStage, ChatTurnStatus

ChatLifecycleState = ChatTurnStatus


class ChatSSEEventType(str, Enum):
    STATE = "state"
    STAGE = "stage"
    RUN_STARTED = "run_started"
    CANCELLED = "cancelled"  # compatibility terminal signal; state is authoritative
    USER_MESSAGE = "user_message"
    DELTA = "delta"
    PAUSE = "pause"
    FINAL = "final"
    CACHED = "cached"
    ERROR = "error"


class UserMessagePayload(BaseModel):
    message_id: str
    created_at: Optional[str] = None


class RunStartedPayload(BaseModel):
    run_id: str
    status: ChatLifecycleState = ChatLifecycleState.RUNNING


class CancelledPayload(BaseModel):
    run_id: str


class RuntimeProgressPayload(BaseModel):
    """A safe runtime activity under a normalized chat execution stage."""

    run_id: str
    stage: ChatExecutionStage
    action: str
    description: str
    outcome: Optional[str] = None


class ChatStatePayload(BaseModel):
    run_id: str
    status: ChatLifecycleState
    stage: Optional[ChatExecutionStage] = None
    activity: Optional[RuntimeProgressPayload] = None
    pause_reason: Optional[str] = None
    user_message_id: Optional[str] = None


class ActiveChatRunSnapshot(BaseModel):
    run_id: str
    turn_id: str
    status: ChatLifecycleState
    user_message_id: Optional[str] = None
    stage: Optional[ChatExecutionStage] = None
    activity: Optional[RuntimeProgressPayload] = None


class ActiveChatRunResponse(BaseModel):
    run: Optional[ActiveChatRunSnapshot] = None


class StagePayload(BaseModel):
    activity: RuntimeProgressPayload


class DeltaPayload(BaseModel):
    content: str = ""


class PausePayload(BaseModel):
    run_id: str
    status: ChatLifecycleState
    reason: str
    action: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    contract_version: int


class FinalPayload(BaseModel):
    message_id: str
    # FINAL is authoritative. Delta is an optional rendering optimization,
    # therefore a client reconnecting or a non-streaming provider must still
    # receive the complete answer here.
    content: str = ""
    created_at: Optional[str] = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    status: ChatLifecycleState = ChatLifecycleState.COMPLETED


class CachedPayload(BaseModel):
    user_message_id: str
    assistant_message_id: str


class ErrorPayload(BaseModel):
    error: str
    code: Optional[str] = None
    recoverable: Optional[bool] = None
    status: ChatLifecycleState = ChatLifecycleState.FAILED


def format_chat_sse(event_type: ChatSSEEventType, payload: BaseModel) -> str:
    import json

    if event_type is ChatSSEEventType.DELTA:
        content = payload.content if isinstance(payload, DeltaPayload) else ""
        lines = ["event: delta\n"]
        for line in content.splitlines():
            lines.append(f"data: {line}\n")
        if content.endswith("\n"):
            lines.append("data:\n")
        lines.append("\n")
        return "".join(lines)
    return f"event: {event_type.value}\ndata: {json.dumps(payload.model_dump(mode='json'), ensure_ascii=False)}\n\n"


def format_chat_sse_done() -> str:
    return "event: done\ndata: [DONE]\n\n"
