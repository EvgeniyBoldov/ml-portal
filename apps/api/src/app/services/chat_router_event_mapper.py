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

def _legacy_action_type(kind: Any, explicit: Any) -> Optional[str]:
    if explicit:
        return str(explicit)
    text = str(kind or "").strip()
    if not text:
        return None
    if text == "call_agent":
        return "agent_call"
    if text == "final":
        return "finalize"
    if text in {"ask_user", "clarify"}:
        return "ask_user"
    return text


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
    if et in {"planner_action", "planner_decision"}:
        agent_slug = event.get("agent_slug")
        kind = event.get("kind")
        step_type = event.get("step_type") or kind
        rationale = event.get("rationale")
        return format_chat_sse(
            ChatSSEEventType.PLANNER_ACTION,
            PlannerActionPayload(
                iteration=event.get("iteration"),
                kind=kind,
                rationale=rationale,
                risk=event.get("risk"),
                contract_version=int(event.get("contract_version") or 1),
                action_type=_legacy_action_type(kind, event.get("action_type")),
                step_type=step_type or event.get("step_kind"),
                agent_slug=agent_slug,
                phase_id=event.get("phase_id"),
                phase_title=event.get("phase_title"),
                why=event.get("why") or rationale,
                question=event.get("question"),
                tool_slug=event.get("tool_slug") or agent_slug,
                op=event.get("op") or step_type or event.get("action_type") or kind,
                execution_mode=event.get("execution_mode"),
                hypotheses=event.get("hypotheses"),
                selected_hypothesis_index=event.get("selected_hypothesis_index"),
                selected_action_kind=event.get("selected_action_kind"),
                selected_action_summary=event.get("selected_action_summary"),
                selection_rationale=event.get("selection_rationale"),
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
            ConfirmationRequiredPayload(
                message=event.get("message"),
                operation_fingerprint=event.get("operation_fingerprint"),
                tool_slug=event.get("tool_slug"),
                operation=event.get("operation"),
                risk_level=event.get("risk_level"),
                args_preview=event.get("args_preview"),
                summary=event.get("summary"),
                run_id=event.get("run_id"),
                orchestration_envelope=event.get("orchestration_envelope"),
                orchestration_state=event.get("orchestration_state"),
            ),
        )
    if et == "waiting_input":
        return format_chat_sse(
            ChatSSEEventType.WAITING_INPUT,
            WaitingInputPayload(
                question=event.get("question"),
                reason=event.get("reason"),
                run_id=event.get("run_id"),
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
                attachments=event.get("attachments", []),
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
                recoverable=event.get("recoverable"),
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
    if action == "input":
        return user_input

    return "Подтверждаю."
