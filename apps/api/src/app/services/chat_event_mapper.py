from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents import RuntimeEvent, RuntimeEventType


class ChatEventMapper:
    """Map runtime events into chat service events."""

    def map_runtime_event(self, event: RuntimeEvent) -> Optional[Dict[str, Any]]:
        if event.type == RuntimeEventType.STATUS:
            return {"type": "status", "stage": event.data.get("stage")}

        if event.type == RuntimeEventType.THINKING:
            return {"type": "status", "stage": f"thinking_step_{event.data.get('step')}"}

        if event.type == RuntimeEventType.OPERATION_CALL:
            return {
                "type": "operation_call",
                "operation": event.data.get("operation"),
                "call_id": event.data.get("call_id"),
                "arguments": event.data.get("arguments"),
            }

        if event.type == RuntimeEventType.OPERATION_RESULT:
            return {
                "type": "operation_result",
                "operation": event.data.get("operation"),
                "call_id": event.data.get("call_id"),
                "success": event.data.get("success"),
                "data": event.data.get("data"),
            }

        if event.type == RuntimeEventType.DELTA:
            return {"type": "delta", "content": event.data.get("content")}

        if event.type == RuntimeEventType.ERROR:
            return {"type": "error", "error": event.data.get("error")}

        if event.type == RuntimeEventType.PLANNER_ACTION:
            return {
                "type": "planner_action",
                "iteration": event.data.get("iteration"),
                "action_type": event.data.get("action_type"),
                "agent_slug": event.data.get("agent_slug"),
                "phase_id": event.data.get("phase_id"),
                "phase_title": event.data.get("phase_title"),
            }

        if event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
            return {
                "type": "confirmation_required",
                "reason": event.data.get("reason"),
                "action": event.data.get("action"),
            }

        if event.type == RuntimeEventType.WAITING_INPUT:
            return {
                "type": "waiting_input",
                "question": event.data.get("question"),
                "reason": event.data.get("reason"),
            }

        if event.type == RuntimeEventType.STOP:
            return {
                "type": "stop",
                "reason": event.data.get("reason"),
                "message": event.data.get("message"),
                "question": event.data.get("question"),
                "run_id": event.data.get("run_id"),
            }

        return None
