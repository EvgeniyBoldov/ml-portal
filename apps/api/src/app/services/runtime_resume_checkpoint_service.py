from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class RuntimeResumeCheckpointService:
    """Builds immutable checkpoint payload for paused-run continuation."""

    def build(
        self,
        *,
        run_id: UUID,
        agent_slug: str,
        tenant_id: Any,
        user_id: Any,
        chat_id: Any,
        paused_action: Optional[Dict[str, Any]],
        paused_context: Optional[Dict[str, Any]],
        resume_action: str,
        user_input: Optional[str] = None,
        source_context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_snapshot = source_context_snapshot if isinstance(source_context_snapshot, dict) else {}
        source_inputs = source_snapshot.get("inputs") if isinstance(source_snapshot.get("inputs"), dict) else {}
        source_meta = source_snapshot.get("meta") if isinstance(source_snapshot.get("meta"), dict) else {}

        payload: Dict[str, Any] = {
            "checkpoint_id": str(uuid4()),
            "source_run_id": str(run_id),
            "agent_slug": agent_slug,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "chat_id": str(chat_id) if chat_id else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resume_action": resume_action,
            "paused_action": paused_action or {},
            "paused_context": paused_context or {},
            "source_context_snapshot": source_snapshot or {},
        }
        original_goal = (
            source_inputs.get("goal")
            or source_inputs.get("user_request")
            or source_meta.get("goal")
        )
        if original_goal:
            payload["original_goal"] = str(original_goal)
        original_user_request = source_inputs.get("user_request")
        if original_user_request:
            payload["original_user_request"] = str(original_user_request)
        if user_input:
            payload["user_input"] = user_input
        return payload
