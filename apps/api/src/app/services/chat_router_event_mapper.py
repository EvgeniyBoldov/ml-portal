"""Serialize the small public chat transport surface.

Runtime journal events never pass this boundary; chat receives only safe
progress plus answer and HITL transport events.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.schemas.chat_events import (
    CachedPayload, ChatSSEEventType, ChatTitlePayload, DeltaPayload, ErrorPayload,
    FinalPayload, PausePayload, RuntimeProgressPayload, StatusPayload,
    UserMessagePayload, format_chat_sse,
)
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService


def map_service_event_to_sse(event: Dict[str, Any]) -> Optional[str]:
    event_type = event.get("type")
    if event_type == "user_message":
        return format_chat_sse(ChatSSEEventType.USER_MESSAGE, UserMessagePayload(
            message_id=str(event["message_id"]), created_at=event.get("created_at"),
        ))
    if event_type == "chat_title":
        return format_chat_sse(ChatSSEEventType.CHAT_TITLE, ChatTitlePayload(title=str(event.get("title") or "")))
    if event_type == "status" and event.get("stage") == "runtime_progress":
        progress = event.get("progress")
        if not isinstance(progress, dict):
            return None
        return format_chat_sse(ChatSSEEventType.STATUS, StatusPayload(progress=RuntimeProgressPayload(
            run_id=str(progress.get("run_id") or ""), phase=str(progress.get("phase") or ""),
            kind=str(progress.get("kind") or ""), description=str(progress.get("description") or ""),
            status=progress.get("status"),
        )))
    if event_type == "delta":
        return format_chat_sse(ChatSSEEventType.DELTA, DeltaPayload(content=str(event.get("content") or "")))
    if event_type in {"stop", "run_paused"}:
        paused = RuntimeHitlProtocolService.build_paused_from_stop(event)
        return format_chat_sse(ChatSSEEventType.PAUSE, PausePayload(
            run_id=str(paused["run_id"]), reason=str(paused["reason"]),
            action=dict(paused["action"]), context=dict(paused["context"]),
            contract_version=int(paused["contract_version"]),
        ))
    if event_type == "final":
        return format_chat_sse(ChatSSEEventType.FINAL, FinalPayload(
            message_id=str(event["message_id"]), created_at=event.get("created_at"),
            sources=list(event.get("sources") or []), attachments=list(event.get("attachments") or []),
        ))
    if event_type == "cached":
        return format_chat_sse(ChatSSEEventType.CACHED, CachedPayload(
            user_message_id=str(event["user_message_id"]), assistant_message_id=str(event["assistant_message_id"]),
        ))
    if event_type == "error":
        return format_chat_sse(ChatSSEEventType.ERROR, ErrorPayload(
            error=str(event.get("error") or "Runtime error"), code=event.get("code"),
            recoverable=event.get("recoverable"),
        ))
    return None


def build_resume_content(*, action: str, user_input: str, paused_action: Optional[Dict[str, Any]], paused_context: Optional[Dict[str, Any]]) -> str:
    return user_input if action == "input" else "Подтверждаю."
