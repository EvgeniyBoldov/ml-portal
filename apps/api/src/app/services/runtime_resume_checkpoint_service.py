from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.schemas.runtime_continuation import RuntimeResumeAction
from app.runtime.plan_store import SqlPlanStore


class RuntimeResumeValidationError(ValueError):
    """A continuation action does not match the persisted pause state."""


class RuntimeResumeCheckpointService:
    """Builds immutable checkpoint payload for paused-run continuation."""

    def __init__(self, *, plan_store: Optional[SqlPlanStore] = None) -> None:
        self._plan_store = plan_store

    @classmethod
    def from_session(cls, session: Any) -> "RuntimeResumeCheckpointService":
        return cls(plan_store=SqlPlanStore(session))

    async def resolve_original_goal(self, run_id: UUID) -> Optional[str]:
        """Read the durable plan goal without making transports inspect plans."""
        if self._plan_store is None:
            return None
        plan = await self._plan_store.get_by_run(run_id)
        if plan is None:
            return None
        goal = str(plan.goal or "").strip()
        return goal or None

    @staticmethod
    def validate_action(
        *,
        pause_status: str,
        action: RuntimeResumeAction,
        user_input: Optional[str],
    ) -> str:
        normalized_status = str(pause_status or "").strip()
        normalized_input = str(user_input or "").strip()
        if normalized_status == "waiting_input":
            if action is RuntimeResumeAction.CANCEL:
                return ""
            if action is not RuntimeResumeAction.INPUT:
                raise RuntimeResumeValidationError("waiting_input requires action='input' or action='cancel'")
            if not normalized_input:
                raise RuntimeResumeValidationError("input is required for action='input'")
            return normalized_input
        if normalized_status == "waiting_confirmation":
            if action not in {RuntimeResumeAction.CONFIRM, RuntimeResumeAction.CANCEL}:
                raise RuntimeResumeValidationError(
                    "waiting_confirmation requires action='confirm' or action='cancel'"
                )
            return ""
        raise RuntimeResumeValidationError("Run is not waiting for resume")

    @staticmethod
    def source_context_snapshot(
        *,
        goal: str,
        execution_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Keep the original goal separate from the user's continuation answer."""
        normalized_goal = str(goal or "").strip()
        snapshot: Dict[str, Any] = {
            "inputs": {
                "goal": normalized_goal,
                "user_request": normalized_goal,
            }
        }
        if execution_mode:
            snapshot["meta"] = {"execution_mode": str(execution_mode)}
        return snapshot

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
