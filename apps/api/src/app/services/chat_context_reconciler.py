"""Revision-guarded persistence for deterministic chat-context operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.chat_memory import ChatMemoryItem
from app.repositories.chat_context_repository import ChatContextRepository
from app.services.chat_context_contracts import ChatContextApplyReceipt, ChatContextOperation


class ChatContextReconciler:
    def __init__(self, repository: ChatContextRepository) -> None:
        self._repository = repository

    async def apply(
        self, *, chat_id: str, branch_id: str | None, chat_turn_id: str,
        expected_revision: int, operations: list[ChatContextOperation],
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
                source = self._source_columns(operation.source_ids, chat_turn_id)
            except (TypeError, ValueError):
                skipped += 1
                continue
            existing = await self._repository.active_item(
                chat_id=chat_id, branch_id=branch_id, kind=operation.kind, item_key=operation.item_key,
            )
            if operation.action in {"close", "expire", "supersede"}:
                if existing:
                    existing.status = {"close": "closed", "expire": "expired", "supersede": "superseded"}[operation.action]
                    self._apply_provenance(existing, source, operation.source_ids, next_order)
                    existing.source_turn_order = next_order
                    applied += 1
                else:
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
    def _source_columns(source_ids: list[str], chat_turn_id: str) -> dict[str, object]:
        """Translate validated opaque sources into indexed provenance columns."""
        columns: dict[str, object] = {"source_turn_id": uuid.UUID(chat_turn_id), "source_message_id": None, "source_run_id": None}
        for source_id in source_ids:
            prefix, value = source_id.split(":", 1)
            if prefix == "turn":
                if uuid.UUID(value) != columns["source_turn_id"]:
                    raise ValueError("operation cannot claim another chat turn")
            elif prefix == "message":
                columns["source_message_id"] = uuid.UUID(value)
            elif prefix == "run":
                columns["source_run_id"] = uuid.UUID(value)
        return columns

    @staticmethod
    def _apply_provenance(
        item: ChatMemoryItem, source: dict[str, object], source_ids: list[str], order: int,
    ) -> None:
        item.source_turn_id = source["source_turn_id"]  # type: ignore[assignment]
        item.source_message_id = source["source_message_id"]  # type: ignore[assignment]
        item.source_run_id = source["source_run_id"]  # type: ignore[assignment]
        item.source_ref = ",".join(source_ids)[:2000] or None
        item.source_turn_order = order
