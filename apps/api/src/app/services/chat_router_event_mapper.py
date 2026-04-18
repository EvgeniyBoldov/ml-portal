from __future__ import annotations

from typing import Any, Dict, Optional

from app.schemas.chat_events import (
    AgentSelectedPayload,
    CachedPayload,
    ChatSSEEventType,
    ConfirmationRequiredPayload,
    DeltaPayload,
    ErrorPayload,
    FinalPayload,
    PlannerActionPayload,
    StatusPayload,
    StopPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
    WaitingInputPayload,
    ChatTitlePayload,
    format_chat_sse,
)


def map_service_event_to_sse(event: Dict[str, Any]) -> Optional[str]:
    """Map ChatStreamService dict event to typed SSE frame."""
    et = event.get("type")
    if not et:
        return None

    if et == "user_message":
        return format_chat_sse(
            ChatSSEEventType.USER_MESSAGE,
            UserMessagePayload(message_id=event["message_id"], created_at=event.get("created_at")),
        )
    if et == "chat_title":
        return format_chat_sse(
            ChatSSEEventType.CHAT_TITLE,
            ChatTitlePayload(title=event.get("title", "")),
        )
    if et == "status":
        return format_chat_sse(
            ChatSSEEventType.STATUS,
            StatusPayload(
                stage=event.get("stage", ""),
                orchestration_envelope=event.get("orchestration_envelope"),
                orchestration_state=event.get("orchestration_state"),
            ),
        )
    if et == "agent_selected":
        return format_chat_sse(
            ChatSSEEventType.AGENT_SELECTED,
            AgentSelectedPayload(agent=event.get("agent"), auto=event.get("auto", False)),
        )
    if et in {"tool_call", "operation_call"}:
        return format_chat_sse(
            ChatSSEEventType.TOOL_CALL,
            ToolCallPayload(
                tool=event.get("tool") or event.get("operation"),
                call_id=event.get("call_id"),
                arguments=event.get("arguments"),
            ),
        )
    if et in {"tool_result", "operation_result"}:
        return format_chat_sse(
            ChatSSEEventType.TOOL_RESULT,
            ToolResultPayload(
                tool=event.get("tool") or event.get("operation"),
                call_id=event.get("call_id"),
                success=event.get("success"),
                data=event.get("data"),
            ),
        )
    if et == "planner_action":
        agent_slug = event.get("agent_slug")
        step_type = event.get("step_type")
        return format_chat_sse(
            ChatSSEEventType.PLANNER_ACTION,
            PlannerActionPayload(
                iteration=event.get("iteration"),
                action_type=event.get("action_type"),
                step_type=step_type,
                agent_slug=agent_slug,
                phase_id=event.get("phase_id"),
                phase_title=event.get("phase_title"),
                why=event.get("why"),
                tool_slug=event.get("tool_slug") or agent_slug,
                op=event.get("op") or step_type or event.get("action_type"),
                orchestration_envelope=event.get("orchestration_envelope"),
                orchestration_state=event.get("orchestration_state"),
            ),
        )
    if et == "delta":
        return format_chat_sse(
            ChatSSEEventType.DELTA,
            DeltaPayload(content=str(event.get("content", ""))),
        )
    if et == "confirmation_required":
        return format_chat_sse(
            ChatSSEEventType.CONFIRMATION_REQUIRED,
            ConfirmationRequiredPayload(reason=event.get("reason"), action=event.get("action")),
        )
    if et == "waiting_input":
        return format_chat_sse(
            ChatSSEEventType.WAITING_INPUT,
            WaitingInputPayload(
                question=event.get("question"),
                reason=event.get("reason"),
                orchestration_envelope=event.get("orchestration_envelope"),
                orchestration_state=event.get("orchestration_state"),
            ),
        )
    if et == "stop":
        return format_chat_sse(
            ChatSSEEventType.STOP,
            StopPayload(
                reason=event.get("reason"),
                message=event.get("message"),
                question=event.get("question"),
                run_id=event.get("run_id"),
                orchestration_envelope=event.get("orchestration_envelope"),
                orchestration_state=event.get("orchestration_state"),
            ),
        )
    if et == "final":
        return format_chat_sse(
            ChatSSEEventType.FINAL,
            FinalPayload(
                message_id=event["message_id"],
                created_at=event.get("created_at"),
                sources=event.get("sources", []),
            ),
        )
    if et == "cached":
        return format_chat_sse(
            ChatSSEEventType.CACHED,
            CachedPayload(
                user_message_id=event["user_message_id"],
                assistant_message_id=event["assistant_message_id"],
            ),
        )
    if et == "error":
        return format_chat_sse(
            ChatSSEEventType.ERROR,
            ErrorPayload(
                error=event.get("error", "Unknown error"),
                code=event.get("code"),
                details=event.get("details"),
            ),
        )
    return None


def build_resume_content(
    *,
    action: str,
    user_input: str,
    paused_action: Optional[Dict[str, Any]],
    paused_context: Optional[Dict[str, Any]],
) -> str:
    question = ""
    if isinstance(paused_context, dict):
        question = str(paused_context.get("question") or paused_context.get("message") or "").strip()
    if not question and isinstance(paused_action, dict):
        question = str(paused_action.get("question") or paused_action.get("message") or "").strip()

    if action == "input":
        if question:
            return f"Уточнение пользователя на вопрос '{question}': {user_input}"
        return user_input

    if question:
        return f"Пользователь подтверждает выполнение. Контекст подтверждения: {question}"
    return "Пользователь подтверждает выполнение. Продолжай выполнение задачи."
