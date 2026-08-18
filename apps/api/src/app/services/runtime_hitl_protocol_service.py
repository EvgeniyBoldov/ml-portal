from __future__ import annotations

from typing import Any, Dict, Optional


class RuntimeHitlProtocolService:
    """Canonical HITL protocol helpers shared by chat/sandbox/resume paths."""

    CONTRACT_VERSION = 1

    @classmethod
    def build_paused_from_stop(cls, stop_payload: Dict[str, Any]) -> Dict[str, Any]:
        reason = str(stop_payload.get("reason") or "").strip() or "paused"
        action_kind = cls._action_kind_for_reason(reason)

        action: Dict[str, Any] = {
            "kind": action_kind,
            "type": "resume",  # legacy alias
            "reason": reason,
            "question": stop_payload.get("question"),
            "message": stop_payload.get("message"),
            "contract_version": cls.CONTRACT_VERSION,
        }
        existing_action = stop_payload.get("action")
        if isinstance(existing_action, dict):
            action.update(existing_action)
        for key in ("operation_fingerprint", "tool_slug", "operation", "risk_level", "args_preview", "summary"):
            if stop_payload.get(key) is not None:
                action[key] = stop_payload[key]

        existing_context = stop_payload.get("context")
        context = dict(existing_context) if isinstance(existing_context, dict) else dict(stop_payload or {})
        context.setdefault("contract_version", cls.CONTRACT_VERSION)
        return {
            "reason": reason,
            "run_id": stop_payload.get("run_id"),
            "action": action,
            "context": context,
            "contract_version": cls.CONTRACT_VERSION,
        }

    @staticmethod
    def extract_operation_fingerprint(
        paused_action: Optional[Dict[str, Any]],
        paused_context: Optional[Dict[str, Any]],
    ) -> str:
        if isinstance(paused_action, dict):
            value = str(paused_action.get("operation_fingerprint") or "").strip()
            if value:
                return value
        if isinstance(paused_context, dict):
            value = str(paused_context.get("operation_fingerprint") or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _action_kind_for_reason(reason: str) -> str:
        if reason == "waiting_confirmation":
            return "confirm"
        if reason == "waiting_input":
            return "input"
        return "resume"
