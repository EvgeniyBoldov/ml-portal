"""Safe runtime-to-chat outcome projection. Never consumes the event journal."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.runtime.turn_state import RuntimeTurnState
from app.runtime.redactor import RuntimeRedactor


def _verified_artifacts(task_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize only runtime-verified artifact DTO variants.

    Agent/tool adapters historically used both ``artifact_id`` and
    ``artifact_ref`` and may nest the collection beneath ``verified``.  Raw
    task output is deliberately not considered here: registry accessibility
    alone is not provenance that the current run produced or used a file.
    """
    verified = task_result.get("verified") if isinstance(task_result.get("verified"), dict) else {}
    candidates = verified.get("artifacts") or verified.get("artifact_refs") or []
    result: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifact_id") or item.get("artifact_ref") or "").strip()
        if not artifact_id:
            continue
        result.append({
            "artifact_id": artifact_id,
            "file_name": str(item.get("file_name") or item.get("name") or "")[:255],
            "content_type": str(item.get("content_type") or "")[:255] or None,
            "size_bytes": item.get("size_bytes") if isinstance(item.get("size_bytes"), int) else None,
            "role": str(item.get("role") or "generated")[:64],
        })
    return result


class RuntimeOutcomeProjection(BaseModel):
    schema_version: int = 1
    run_id: str
    chat_id: str
    chat_turn_id: str
    user_message_id: str | None = None
    current_user_intent: str = ""
    terminal_state: Literal["completed", "waiting_input", "waiting_confirmation", "failed"]
    effective_goal: str = ""
    project_context: dict[str, Any] = Field(default_factory=dict)
    term_bindings: list[dict[str, Any]] = Field(default_factory=list)
    clarification: Optional[dict[str, Any]] = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    deleted_artifact_ids: list[str] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)
    task_result_refs: list[dict[str, Any]] = Field(default_factory=list)
    assistant_outcome: dict[str, Any] = Field(default_factory=dict)


class RuntimeOutcomeProjector:
    """Pure projection from canonical runtime state and terminal decision."""

    @staticmethod
    def project(
        *, runtime_state: RuntimeTurnState, chat_id: str, chat_turn_id: str,
        terminal_state: Literal["completed", "waiting_input", "waiting_confirmation", "failed"],
        project_context: Optional[dict[str, Any]] = None,
        term_bindings: Optional[list[dict[str, Any]]] = None,
        clarification: Optional[dict[str, Any]] = None,
        user_message_id: str | None = None,
        current_user_intent: str = "",
    ) -> RuntimeOutcomeProjection:
        redactor = RuntimeRedactor()
        artifacts: list[dict[str, Any]] = []
        for item in runtime_state.attachment_contexts:
            ref = item.ref
            artifacts.append({
                "artifact_id": ref.artifact_id,
                "file_name": ref.file_name,
                "content_type": ref.content_type,
                "size_bytes": ref.size_bytes,
                "role": "attachment",
            })
        for result in runtime_state.task_results:
            if not isinstance(result, dict):
                continue
            artifacts.extend(_verified_artifacts(result))
        limitations = []
        for item in runtime_state.task_results:
            if not isinstance(item, dict) or item.get("outcome") not in {"blocked", "unfulfillable"}:
                continue
            limitation = item.get("limitation") if isinstance(item.get("limitation"), dict) else {}
            message = limitation.get("user_message") or limitation.get("message") or item.get("summary") or item.get("description") or ""
            limitations.append({
                "reason_code": str(limitation.get("reason_code") or item.get("reason_code") or "blocked"),
                "user_message": str(redactor.redact(message))[:600],
            })
        task_result_refs = []
        for item in runtime_state.task_results:
            if not isinstance(item, dict):
                continue
            outcome = str(item.get("outcome") or "")
            plan_id = str(item.get("plan_id") or "").strip()
            task_entity_id = str(item.get("task_entity_id") or item.get("task_id") or "").strip()
            if outcome not in {"completed", "unfulfillable"} or not plan_id or not task_entity_id:
                continue
            artifact_ids = [
                str(artifact["artifact_id"])
                for artifact in _verified_artifacts(item)
            ]
            task_result_refs.append({
                "plan_id": plan_id, "task_entity_id": task_entity_id, "outcome": outcome,
                "safe_summary": str(redactor.redact(item.get("description") or ""))[:600], "artifact_ids": artifact_ids[:10],
                "source_run_id": str(runtime_state.run_id),
            })
        return RuntimeOutcomeProjection(
            run_id=str(runtime_state.run_id), chat_id=chat_id, chat_turn_id=chat_turn_id,
            user_message_id=user_message_id,
            current_user_intent=str(redactor.redact(current_user_intent))[:1200],
            terminal_state=terminal_state, effective_goal=runtime_state.goal[:1200],
            project_context=dict(project_context or {}), term_bindings=list(term_bindings or [])[:20], clarification=dict(clarification or {}) or None,
            artifacts=artifacts[:50], deleted_artifact_ids=list(runtime_state.deleted_artifact_ids)[:50],
            limitations=limitations[:5], task_result_refs=task_result_refs[:20],
            assistant_outcome={"summary": str(redactor.redact(runtime_state.final_answer or ""))[:1200]},
        )
