"""Public, typed SSE contract for chat execution."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatSSEEventType(str, Enum):
    USER_MESSAGE = "user_message"
    CHAT_TITLE = "chat_title"
    STATUS = "status"
    DELTA = "delta"
    PAUSE = "pause"
    FINAL = "final"
    CACHED = "cached"
    ERROR = "error"


class UserMessagePayload(BaseModel):
    message_id: str
    created_at: Optional[str] = None


class ChatTitlePayload(BaseModel):
    title: str


class RuntimeProgressPayload(BaseModel):
    """Bounded, redacted projection from ``RuntimeProgressStreamer``."""

    run_id: str
    phase: str
    kind: str
    description: str
    status: Optional[str] = None


class StatusPayload(BaseModel):
    stage: str = "runtime_progress"
    progress: RuntimeProgressPayload


class DeltaPayload(BaseModel):
    content: str = ""


class PausePayload(BaseModel):
    run_id: str
    reason: str
    action: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    contract_version: int


class FinalPayload(BaseModel):
    message_id: str
    created_at: Optional[str] = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class CachedPayload(BaseModel):
    user_message_id: str
    assistant_message_id: str


class ErrorPayload(BaseModel):
    error: str
    code: Optional[str] = None
    recoverable: Optional[bool] = None


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
