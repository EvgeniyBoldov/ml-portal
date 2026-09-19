"""Deterministic translation of verified runtime outcomes into context operations."""
from __future__ import annotations

from typing import Any

from app.runtime.context_outcome import RuntimeOutcomeProjection
from app.services.chat_context_contracts import ChatContextOperation


class ChatContextReducer:
    def reduce(self, *, projection: RuntimeOutcomeProjection, expected_revision: int) -> list[ChatContextOperation]:
        operations: list[ChatContextOperation] = []
        source = [f"run:{projection.run_id}", f"turn:{projection.chat_turn_id}"]
        if projection.user_message_id:
            source.append(f"message:{projection.user_message_id}")
        keys = projection.project_context.get("explicit_project_keys") or []
        normalized = list(dict.fromkeys(str(value).strip().casefold() for value in keys if str(value).strip()))
        if normalized:
            operations.append(ChatContextOperation(action="update", kind="scope", item_key="current_scope",
                payload={"project_keys": normalized, "source": "explicit", "trust_class": "application_verified"}, source_ids=source, expected_revision=expected_revision))
        for binding in projection.term_bindings:
            entry_id = str(binding.get("id") or binding.get("glossary_entry_id") or "").strip()
            term = str(binding.get("term") or "").strip()
            if entry_id and term:
                operations.append(ChatContextOperation(action="touch", kind="term_binding", item_key=entry_id,
                    payload={"glossary_entry_id": entry_id, "term": term, "aliases": list(binding.get("matched_aliases") or binding.get("aliases") or [])[:10], "trust_class": "application_verified"}, source_ids=[*source, f"glossary:{entry_id}"], expected_revision=expected_revision))
        if projection.effective_goal:
            # A completed run is not necessarily a completed conversational
            # objective: follow-up requests must keep an explicit active goal.
            operations.append(ChatContextOperation(action="update", kind="goal", item_key="active_goal",
                payload={"text": projection.effective_goal, "status": "active", "trust_class": "runtime_normalized"}, source_ids=source, expected_revision=expected_revision))
        if projection.clarification:
            operations.append(ChatContextOperation(action="touch", kind="open_loop", item_key=f"turn:{projection.chat_turn_id}",
                payload={"status": "waiting", "user_message": str(projection.clarification.get("question") or projection.clarification.get("message") or "")[:600], "trust_class": "application_verified"}, source_ids=source, expected_revision=expected_revision))
        elif projection.terminal_state == "completed":
            operations.append(ChatContextOperation(action="close", kind="open_loop", item_key=f"turn:{projection.chat_turn_id}", source_ids=source, expected_revision=expected_revision))
        for limitation in projection.limitations:
            message = str(limitation.get("user_message") or "").strip()
            if message:
                operations.append(ChatContextOperation(action="touch", kind="open_loop", item_key=f"blocked:{projection.run_id}",
                    payload={"status": "blocked", "reason_code": str(limitation.get("reason_code") or "blocked"), "user_message": message[:600], "trust_class": "runtime_normalized"}, source_ids=source, expected_revision=expected_revision))
        for artifact in projection.artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("artifact_id") or artifact.get("id") or "").strip()
            if artifact_id:
                operations.append(ChatContextOperation(action="touch", kind="artifact_ref", item_key=artifact_id,
                    payload={"artifact_id": artifact_id, "role": str(artifact.get("role") or "referenced"), "file_name": str(artifact.get("file_name") or "")[:255], "trust_class": "application_verified"}, source_ids=[*source, f"artifact:{artifact_id}"], expected_revision=expected_revision))
        for artifact_id in projection.deleted_artifact_ids:
            if artifact_id:
                operations.append(ChatContextOperation(action="close", kind="artifact_ref", item_key=artifact_id,
                    source_ids=[*source, f"artifact:{artifact_id}"], expected_revision=expected_revision))
        for item in projection.task_result_refs:
            plan_id = str(item.get("plan_id") or "").strip()
            task_entity_id = str(item.get("task_entity_id") or "").strip()
            if plan_id and task_entity_id:
                operations.append(ChatContextOperation(action="touch", kind="task_result_ref", item_key=f"{plan_id}:{task_entity_id}",
                    payload={**item, "trust_class": "runtime_normalized"},
                    source_ids=[*source, f"task:{task_entity_id}"][:4], expected_revision=expected_revision))
        operations.append(ChatContextOperation(
            action="update", kind="recent_anchor", item_key="recent_anchor",
            payload={
                "user_intent": projection.current_user_intent or projection.effective_goal,
                "assistant_outcome": str(projection.assistant_outcome.get("summary") or ""),
                "terminal_state": projection.terminal_state,
                "trust_class": "runtime_normalized",
            }, source_ids=source, expected_revision=expected_revision,
        ))
        return operations
