from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime import RuntimeEvent, RuntimeEventType
from app.runtime.error_surface import build_user_safe_error_message


def _envelope(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return data.get("_envelope")


class ChatEventMapper:
    """Map runtime v3 events into chat service SSE payloads."""
    _ALLOWED_LLM_FIELDS = {
        "llm_call_id",
        "step",
        "model",
        "temperature",
        "max_tokens",
        "response_length",
        "tokens_in",
        "tokens_out",
        "tokens_total",
        "duration_ms",
        "native_tool_calling",
        "purpose",
        "parent_entity_type",
        "parent_entity_id",
        "planner_iteration_id",
        "planner_run_id",
        "agent_run_id",
        "agent_slug",
        "actor_type",
        "actor_entity_id",
    }

    def map_runtime_event(self, event: RuntimeEvent) -> Optional[Dict[str, Any]]:
        env = _envelope(event.data)

        if event.type == RuntimeEventType.STATUS:
            return {
                "type": "status",
                "stage": event.data.get("stage"),
                "execution_mode": event.data.get("execution_mode"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.TOOL_CALL:
            return {
                "type": "tool_call",
                "tool": event.data.get("tool"),
                "call_id": event.data.get("call_id"),
                "arguments": event.data.get("arguments"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.TOOL_RESULT:
            return {
                "type": "tool_result",
                "tool": event.data.get("tool"),
                "call_id": event.data.get("call_id"),
                "success": event.data.get("success"),
                "data": event.data.get("data"),
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.LLM_TURN:
            payload = {k: v for k, v in event.data.items() if k in self._ALLOWED_LLM_FIELDS}
            return {
                "type": event.type.value,
                **payload,
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
                "error": build_user_safe_error_message(
                    retryable=retryable,
                    error_code=error_code,
                ),
                "recoverable": recoverable,
                "code": error_code,
                "details": {
                    "retryable": retryable,
                    "recoverable": recoverable,
                    "runtime_error_code": error_code,
                },
                "orchestration_envelope": env,
            }

        if event.type == RuntimeEventType.PLANNER_DECISION:
            kind = event.data.get("kind")
            rationale = event.data.get("rationale")
            return {
                "type": "planner_decision",
                "iteration": event.data.get("iteration"),
                "kind": kind,
                "step_kind": event.data.get("stepKind"),
                "rationale": rationale,
                "risk": event.data.get("risk"),
                "execution_mode": event.data.get("execution_mode"),
                "hypotheses": event.data.get("hypotheses"),
                "selected_hypothesis_index": event.data.get("selected_hypothesis_index"),
                "selected_action_kind": event.data.get("selected_action_kind"),
                "selected_action_summary": event.data.get("selected_action_summary"),
                "selection_rationale": event.data.get("selection_rationale"),
                "contract_version": 1,
                "agent_slug": event.data.get("agent_slug"),
                "phase_id": event.data.get("phase_id"),
                "phase_title": event.data.get("phase_title"),
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
