"""Revision-guarded persistence for deterministic chat-context operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.chat_memory import ChatMemoryItem
from app.repositories.chat_context_repository import ChatContextRepository
from app.services.chat_context_contracts import ChatContextApplyReceipt, ChatContextOperation


_SINGLETON_KEYS = {
    "scope": "current_scope",
    "goal": "active_goal",
    "recent_anchor": "recent_anchor",
}
_TRUST_RANK = {
    "model_inferred": 1,
    "runtime_normalized": 2,
    "user_explicit": 3,
    "application_verified": 4,
}


class ChatContextReconciler:
    def __init__(self, repository: ChatContextRepository) -> None:
        self._repository = repository

    async def apply(
        self, *, chat_id: str, branch_id: str | None, chat_turn_id: str,
        expected_revision: int, operations: list[ChatContextOperation], tenant_id: str | None = None,
        project_keys: list[str] | None = None,
    ) -> ChatContextApplyReceipt:
        head = await self._repository.get_or_create_head(chat_id=chat_id, branch_id=branch_id)
        if head.revision != expected_revision:
            return ChatContextApplyReceipt(revision=head.revision, skipped_count=len(operations), degradation_codes=["stale_revision"])
        next_order = head.updated_through_turn_order + 1
        applied = 0
        skipped = 0
        for operation in operations:
            if operation.expected_revision != expected_revision:
                skipped += 1
                continue
            try:
                payload = operation.validated_payload()
                self._validate_canonical_key(operation)
                self._payload_matches_sources(operation, payload)
                existing = await self._repository.active_item(
                    chat_id=chat_id, branch_id=branch_id, kind=operation.kind, item_key=operation.item_key,
                )
                allow_missing_artifacts = (
                    {operation.item_key}
                    if existing is not None
                    and operation.kind == "artifact_ref"
                    and operation.action in {"close", "expire", "supersede"}
                    else set()
                )
                expected_task_refs = (
                    {str(payload.get("task_entity_id")): str(payload.get("plan_id"))}
                    if operation.kind == "task_result_ref" and payload
                    else {}
                )
                source = await self._repository.validate_provenance(
                    chat_id=chat_id, chat_turn_id=chat_turn_id, source_ids=operation.source_ids,
                    tenant_id=tenant_id,
                    project_keys=project_keys,
                    allow_missing_artifact_ids=allow_missing_artifacts,
                    expected_task_refs=expected_task_refs,
                )
            except (TypeError, ValueError):
                skipped += 1
                continue
            if existing and existing.expires_at and existing.expires_at <= datetime.now(timezone.utc):
                # Expiry is effective even before the periodic cleanup task
                # runs.  Flush this lifecycle transition before a new active
                # row is inserted so the partial unique index is never asked
                # to treat stale state as current.
                existing.status = "expired"
                await self._repository.flush()
                existing = None
            if operation.action in {"close", "expire", "supersede"}:
                if existing:
                    existing.status = {"close": "closed", "expire": "expired", "supersede": "superseded"}[operation.action]
                    self._apply_provenance(existing, source, operation.source_ids, next_order)
                    existing.source_turn_order = next_order
                    applied += 1
                else:
                    skipped += 1
                continue
            if existing and self._inferred_cannot_replace(existing.payload or {}, payload, operation.kind):
                skipped += 1
                continue
            if operation.action == "add" and existing is not None:
                # Re-delivery of the same deterministic outcome is harmless;
                # conflicting inference cannot silently overwrite it.
                if dict(existing.payload or {}) == payload:
                    skipped += 1
                    continue
                skipped += 1
                continue
            if existing is None and operation.action == "update" and operation.kind not in {"scope", "goal", "recent_anchor"}:
                skipped += 1
                continue
            if existing is None:
                existing = ChatMemoryItem(
                    chat_id=uuid.UUID(chat_id), sandbox_branch_id=uuid.UUID(branch_id) if branch_id else None,
                    kind=operation.kind, item_key=operation.item_key, payload=payload,
                    confidence=operation.confidence, source_turn_order=next_order,
                    expires_at=operation.expires_at,
                )
                self._apply_provenance(existing, source, operation.source_ids, next_order)
                # Singleton replacement preserves historical provenance.
                if operation.kind in {"scope", "goal", "recent_anchor"}:
                    for item in await self._repository.active_items(chat_id=chat_id, branch_id=branch_id):
                        if item.kind == operation.kind and item.item_key != operation.item_key:
                            item.status = "superseded"
                self._repository.add_item(existing)
            else:
                if operation.kind == "scope" and payload.get("source") == "inferred":
                    # Topic inference may enrich an existing exact focus, but
                    # it must never erase or replace verified project/entity
                    # identity.  The next explicit scope selection replaces
                    # this transient topic through the normal update path.
                    previous = dict(existing.payload or {})
                    payload = {
                        **payload,
                        "project_keys": list(previous.get("project_keys") or []),
                        "project_keys_trust_class": str(previous.get("project_keys_trust_class") or "application_verified"),
                        "entity_refs": list(previous.get("entity_refs") or []),
                        "entity_refs_trust_class": str(previous.get("entity_refs_trust_class") or "application_verified"),
                        "topic_trust_class": "model_inferred",
                        "source": str(previous.get("source") or "inferred") if previous.get("project_keys") else "inferred",
                    }
                    if previous.get("project_keys") or previous.get("entity_refs"):
                        payload["trust_class"] = str(previous.get("trust_class") or "application_verified")
                existing.payload = payload
                existing.confidence = operation.confidence
                existing.expires_at = operation.expires_at
                self._apply_provenance(existing, source, operation.source_ids, next_order)
            applied += 1
        if applied:
            head.revision += 1
            head.updated_through_turn_id = uuid.UUID(chat_turn_id)
            head.updated_through_turn_order = next_order
            await self._repository.flush()
        return ChatContextApplyReceipt(revision=head.revision, applied_count=applied, skipped_count=skipped)

    @staticmethod
    def _validate_canonical_key(operation: ChatContextOperation) -> None:
        expected = _SINGLETON_KEYS.get(operation.kind)
        if expected and operation.item_key != expected:
            raise ValueError(f"{operation.kind} requires canonical item key")

    @staticmethod
    def _inferred_cannot_replace(existing_payload: dict, payload: dict, kind: str) -> bool:
        """Keep LLM inference from overwriting a stronger singleton value."""
        if kind not in {"goal", "recent_anchor"}:
            return False
        incoming = str(payload.get("trust_class") or "runtime_normalized")
        previous = str(existing_payload.get("trust_class") or "runtime_normalized")
        return incoming == "model_inferred" and _TRUST_RANK.get(previous, 0) > _TRUST_RANK[incoming]

    @staticmethod
    def _payload_matches_sources(operation: ChatContextOperation, payload: dict[str, object]) -> None:
        """Bind a typed payload identifier to its typed provenance reference."""
        sources = set(operation.source_ids)
        if operation.kind == "term_binding" and operation.action not in {"close", "expire", "supersede"}:
            if f"glossary:{payload.get('glossary_entry_id')}" not in sources:
                raise ValueError("term binding must cite its glossary entry")
        if operation.kind == "artifact_ref":
            artifact_id = operation.item_key if operation.action in {"close", "expire", "supersede"} else str(payload.get("artifact_id") or "")
            if f"artifact:{artifact_id}" not in sources:
                raise ValueError("artifact item must cite its registry reference")
        if operation.kind == "task_result_ref" and operation.action not in {"close", "expire", "supersede"}:
            if f"task:{payload.get('task_entity_id')}" not in sources:
                raise ValueError("task result must cite its runtime task")

    @staticmethod
    def _apply_provenance(
        item: ChatMemoryItem, source: dict[str, object], source_ids: list[str], order: int,
    ) -> None:
        item.source_turn_id = source["source_turn_id"]  # type: ignore[assignment]
        item.source_message_id = source["source_message_id"]  # type: ignore[assignment]
        item.source_run_id = source["source_run_id"]  # type: ignore[assignment]
        item.source_ref = ",".join(source_ids)[:2000] or None
        item.source_turn_order = order
