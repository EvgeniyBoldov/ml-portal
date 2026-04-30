from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime import RuntimeEvent, RuntimeEventType


def _envelope(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return data.get("_envelope")


class ChatEventMapper:
    """Map runtime v3 events into chat service SSE payloads."""

    @staticmethod
    def _planner_action_type(kind: Any) -> Optional[str]:
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

    def map_runtime_event(self, event: RuntimeEvent) -> Optional[Dict[str, Any]]:
        env = _envelope(event.data)

        if event.type == RuntimeEventType.STATUS:
            return {
                "type": "status",
                "stage": event.data.get("stage"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.OPERATION_CALL:
            return {
                "type": "operation_call",
                "operation": event.data.get("operation"),
                "call_id": event.data.get("call_id"),
                "arguments": event.data.get("arguments"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.OPERATION_RESULT:
            return {
                "type": "operation_result",
                "operation": event.data.get("operation"),
                "call_id": event.data.get("call_id"),
                "success": event.data.get("success"),
                "data": event.data.get("data"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.DELTA:
            return {"type": "delta", "content": event.data.get("content")}

        if event.type == RuntimeEventType.ERROR:
            error_code = event.data.get("error_code")
            retryable = event.data.get("retryable")
            recoverable = event.data.get("recoverable", retryable if retryable is not None else False)
            return {
                "type": "error",
                "error": event.data.get("error"),
                "recoverable": recoverable,
                "code": error_code,
                "details": {
                    "retryable": retryable,
                    "recoverable": recoverable,
                    "runtime_error_code": error_code,
                },
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.PLANNER_STEP:
            kind = event.data.get("kind")
            rationale = event.data.get("rationale")
            action_type = self._planner_action_type(kind)
            return {
                "type": "planner_action",
                "iteration": event.data.get("iteration"),
                "kind": kind,
                "rationale": rationale,
                "risk": event.data.get("risk"),
                "contract_version": 1,
                # legacy aliases
                "action_type": action_type,
                "step_type": kind,
                "agent_slug": event.data.get("agent_slug"),
                "phase_id": event.data.get("phase_id"),
                "phase_title": event.data.get("phase_title"),
                "why": rationale,
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
            return {
                "type": "confirmation_required",
                "message": event.data.get("message"),
                "operation_fingerprint": event.data.get("operation_fingerprint"),
                "tool_slug": event.data.get("tool_slug"),
                "operation": event.data.get("operation"),
                "risk_level": event.data.get("risk_level"),
                "args_preview": event.data.get("args_preview"),
                "summary": event.data.get("summary"),
                "run_id": event.data.get("run_id"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.WAITING_INPUT:
            return {
                "type": "waiting_input",
                "question": event.data.get("question"),
                "reason": event.data.get("reason") or "waiting_input",
                "run_id": event.data.get("run_id"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.STOP:
            return {
                "type": "stop",
                "reason": event.data.get("reason"),
                "message": event.data.get("message"),
                "question": event.data.get("question"),
                "run_id": event.data.get("run_id"),
                "orchestration_envelope": env,
            }

        # FINAL is handled explicitly by ChatStreamService._run_with_router
        return None
