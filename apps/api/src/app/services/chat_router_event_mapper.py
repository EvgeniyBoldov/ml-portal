"""Serialize the small public chat transport surface.

Runtime journal events never pass this boundary; chat receives only safe
progress plus answer and HITL transport events.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.schemas.chat_events import (
    CachedPayload, CancelledPayload, ChatExecutionStage, ChatLifecycleState,
    ChatSSEEventType, ChatStatePayload, DeltaPayload, ErrorPayload,
    FinalPayload, PausePayload, RuntimeProgressPayload, StagePayload,
    RunStartedPayload, UserMessagePayload, format_chat_sse,
)
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService


def map_service_event_to_sse(event: Dict[str, Any]) -> Optional[str]:
    event_type = event.get("type")
    if event_type == "state":
        state = ChatStatePayload(
            run_id=str(event["run_id"]),
            status=ChatLifecycleState(str(event["status"])),
            stage=event.get("stage"),
            activity=event.get("activity"),
            pause_reason=event.get("pause_reason"),
            user_message_id=str(event["user_message_id"]) if event.get("user_message_id") else None,
        )
        return format_chat_sse(ChatSSEEventType.STATE, state)
    if event_type == "stage":
        activity = event.get("activity")
        if not isinstance(activity, dict):
            return None
        return format_chat_sse(ChatSSEEventType.STAGE, StagePayload(
            activity=RuntimeProgressPayload(
                run_id=str(activity.get("run_id") or event.get("run_id") or ""),
                stage=str(activity.get("stage") or "preparing"),
                action=str(activity.get("action") or "runtime_activity"),
                description=str(activity.get("description") or "Выполняю запрос"),
                outcome=activity.get("outcome"),
            ),
        ))
    if event_type == "run_started":
        return format_chat_sse(ChatSSEEventType.RUN_STARTED, RunStartedPayload(
            run_id=str(event["run_id"]),
            status=ChatLifecycleState(str(event.get("status") or "running")),
        ))
    if event_type == "cancelled":
        return format_chat_sse(ChatSSEEventType.CANCELLED, CancelledPayload(
            run_id=str(event["run_id"]),
        ))
    if event_type == "user_message":
        return format_chat_sse(ChatSSEEventType.USER_MESSAGE, UserMessagePayload(
            message_id=str(event["message_id"]), created_at=event.get("created_at"),
        ))
    if event_type == "status" and event.get("stage") == "runtime_progress":
        progress = event.get("progress")
        if not isinstance(progress, dict):
            return None
        phase = str(progress.get("phase") or "")
        stage = {
            "preflight": "planning", "planner": "planning", "planning": "planning",
            "agent": "executing", "execution": "executing", "synthesis": "synthesizing",
            "pipeline": "executing",
        }.get(phase, "preparing")
        return format_chat_sse(ChatSSEEventType.STAGE, StagePayload(activity=RuntimeProgressPayload(
            run_id=str(progress.get("run_id") or ""),
            stage=ChatExecutionStage(stage),
            action=str(progress.get("kind") or "runtime_activity"),
            description=str(progress.get("description") or "Выполняю запрос"),
            outcome=progress.get("status") if progress.get("status") in {"completed", "failed", "cancelled", "error"} else None,
        )))
    if event_type == "delta":
        return format_chat_sse(ChatSSEEventType.DELTA, DeltaPayload(content=str(event.get("content") or "")))
    if event_type in {"stop", "run_paused"}:
        paused = RuntimeHitlProtocolService.public_pause(RuntimeHitlProtocolService.build_paused_from_stop(event))
        # STOP is also emitted for terminal failures. Only the two explicit
        # HITL reasons are resumable; exposing a failed run as `pause` makes
        # clients render a bogus clarification input.
        if paused["reason"] not in {"waiting_input", "waiting_confirmation"}:
            return None
        return format_chat_sse(ChatSSEEventType.PAUSE, PausePayload(
            run_id=str(paused["run_id"]), reason=str(paused["reason"]),
            status=ChatLifecycleState(str(paused["reason"])),
            action=dict(paused["action"]), context=dict(paused["context"]),
            contract_version=int(paused["contract_version"]),
        ))
    if event_type == "final":
        return format_chat_sse(ChatSSEEventType.FINAL, FinalPayload(
            message_id=str(event["message_id"]), created_at=event.get("created_at"),
            content=str(event.get("content") or ""),
            sources=list(event.get("sources") or []), attachments=list(event.get("attachments") or []),
            stop_reason=event.get("stop_reason"),
            status=ChatLifecycleState(str(event.get("status") or (
                "failed" if event.get("stop_reason") == "failed" else "completed"
            ))),
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
