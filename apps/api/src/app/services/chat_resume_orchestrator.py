from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.runtime_terminal_status import (
    ContinuationApiStatus,
    ContinuationTerminalStatus,
    continuation_api_status_from_terminal,
    continuation_terminal_from_event,
)


class ChatResumeOrchestrator:
    """Executes continuation flow for paused chat runs."""

    def __init__(self, chat_stream_service: Any) -> None:
        self.chat_stream_service = chat_stream_service

    async def continue_chat(
        self,
        *,
        run_id: str,
        chat_id: str,
        user_id: str,
        agent_slug: Optional[str],
        resume_content: str,
        checkpoint: Dict[str, Any],
        paused_action: Optional[Dict[str, Any]],
        paused_context: Optional[Dict[str, Any]],
        user_input: Optional[str] = None,
        confirmation_tokens: Optional[list] = None,
    ) -> Dict[str, Any]:
        status = ContinuationTerminalStatus.COMPLETED
        continuation_error: Optional[str] = None
        assistant_message_id: Optional[str] = None
        paused_again_reason: Optional[str] = None
        paused_again_run_id: Optional[str] = None
        paused_again_action: Optional[Dict[str, Any]] = None
        paused_again_context: Optional[Dict[str, Any]] = None

        async for event in self.chat_stream_service.send_message_stream(
            chat_id=chat_id,
            user_id=user_id,
            content=resume_content,
            attachment_ids=[],
            idempotency_key=None,
            model=None,
            agent_slug=agent_slug,
            continuation_meta={
                "resume_checkpoint": checkpoint,
                "resumed_from_run_id": run_id,
            },
            confirmation_tokens=list(confirmation_tokens or []),
        ):
            terminal = continuation_terminal_from_event(event)
            if terminal:
                status, continuation_error = terminal

            event_type = event.get("type")
            if event_type == "final":
                assistant_message_id = str(event.get("message_id")) if event.get("message_id") else None
            elif event_type == "run_paused":
                paused_again_reason = str(event.get("reason") or "")
                paused_again_run_id = str(event.get("run_id") or "")
                paused_again_action = event.get("action") if isinstance(event.get("action"), dict) else None
                paused_again_context = event.get("context") if isinstance(event.get("context"), dict) else None

        payload: Dict[str, Any] = {
            "run_id": run_id,
            "paused_action": paused_action,
            "paused_context": paused_context,
            "resume_checkpoint": checkpoint,
        }
        if user_input:
            payload["user_input"] = user_input

        api_status = continuation_api_status_from_terminal(status)
        if api_status == ContinuationApiStatus.RESUMED_WITH_ERROR:
            payload["status"] = api_status.value
            payload["error"] = continuation_error
            return payload

        if api_status == ContinuationApiStatus.RESUMED_PAUSED_AGAIN:
            payload["status"] = api_status.value
            payload["paused_again_reason"] = paused_again_reason
            payload["paused_again_run_id"] = paused_again_run_id
            payload["paused_again_action"] = paused_again_action
            payload["paused_again_context"] = paused_again_context
            return payload

        payload["status"] = api_status.value
        if assistant_message_id:
            payload["assistant_message_id"] = assistant_message_id
        return payload
