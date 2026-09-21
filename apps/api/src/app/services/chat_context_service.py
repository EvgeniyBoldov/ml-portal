from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.repositories.chats_repo import AsyncChatMessagesRepository
from app.repositories.chat_context_repository import ChatContextRepository
from app.services.chat_context_contracts import ChatContextApplyReceipt, ChatContextOperation, ChatContextSnapshot
from app.services.chat_context_reconciler import ChatContextReconciler
from app.runtime.context_outcome import RuntimeOutcomeProjection
from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
from app.core.config import get_settings

logger = get_logger(__name__)


class ChatContextService:
    """Read and reconcile the canonical bounded chat context."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClientProtocol | None,
        messages_repo: AsyncChatMessagesRepository | None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.messages_repo = messages_repo

    async def load_chat_context(self, chat_id: str | uuid.UUID, limit: int = 20) -> List[Dict[str, Any]]:
        """Load recent messages for LLM context (raw, no summary)."""
        messages = await self.messages_repo.get_recent_chat_messages(
            chat_id=str(chat_id),
            limit=limit,
        )

        context: List[Dict[str, Any]] = []
        for msg in messages:
            if msg.role not in {"user", "assistant"}:
                continue
            content_text = msg.content
            if isinstance(content_text, dict) and "text" in content_text:
                content_text = content_text["text"]
            elif isinstance(content_text, dict):
                content_text = json.dumps(content_text)

            message_id = getattr(msg, "id", None)
            context.append({
                **({"message_id": str(message_id)} if message_id is not None else {}),
                "role": msg.role,
                "content": str(content_text),
                **(
                    {"meta": {"attachments": list(msg.meta.get("attachments") or [])}}
                    if isinstance(getattr(msg, "meta", None), dict)
                    and isinstance(msg.meta.get("attachments"), list)
                    else {}
                ),
            })
        return context

    async def load_snapshot(
        self, *, chat_id: str, branch_id: str | None = None, owner_id: str | None = None,
        tenant_id: str | None = None, _attempt: int = 0,
    ) -> ChatContextSnapshot:
        """Load a bounded immutable context projection; artifact access is fresh.

        A missing principal deliberately yields no artifact candidates.  A
        reference the canonical registry cannot resolve is omitted from this
        projection.  Reads never retire it: inspection and prompt assembly
        must remain side-effect free and lifecycle transitions require an
        explicit writer transaction.
        """
        repository = ChatContextRepository(self.session)
        settings = get_settings()
        head = await repository.get_head(chat_id=chat_id, branch_id=branch_id)
        snapshot = ChatContextSnapshot(chat_id=chat_id, sandbox_branch_id=branch_id, revision=head.revision if head else 0,
            updated_through_turn_id=str(head.updated_through_turn_id) if head and head.updated_through_turn_id else None)
        per_kind_limits = {
            # Singleton values are independently selected.  Do not replace
            # this with a global projection limit: recency of artifacts is
            # not allowed to suppress the active conversational focus.
            "scope": 1,
            "goal": 1,
            "recent_anchor": 1,
            "term_binding": settings.CHAT_CONTEXT_TERM_BINDING_LIMIT,
            "artifact_ref": settings.CHAT_CONTEXT_ARTIFACT_LIMIT,
            "open_loop": settings.CHAT_CONTEXT_OPEN_LOOP_LIMIT,
            "decision": settings.CHAT_CONTEXT_DECISION_LIMIT,
            "task_result_ref": settings.CHAT_CONTEXT_TASK_RESULT_LIMIT,
        }
        counts: dict[str, int] = {}
        items = await repository.active_items_by_kind(
            chat_id=chat_id, branch_id=branch_id, kind_limits=per_kind_limits,
        )
        resolved_artifacts = {}
        if owner_id and tenant_id:
            artifact_ids = [
                str((item.payload or {}).get("artifact_id") or item.item_key)
                for item in items if item.kind == "artifact_ref"
            ]
            resolved_artifacts = await ChatArtifactReferenceService(self.session).resolve_many(
                artifact_ids=artifact_ids, chat_id=chat_id, owner_id=owner_id, tenant_id=tenant_id,
            )
        for item in items:
            count = counts.get(item.kind, 0)
            if count >= per_kind_limits.get(item.kind, 1):
                continue
            payload = dict(item.payload or {})
            if item.kind == "artifact_ref":
                if not owner_id or not tenant_id:
                    continue
                artifact_id = str(payload.get("artifact_id") or item.item_key)
                resolved = resolved_artifacts.get(artifact_id)
                if resolved is None:
                    if len(snapshot.uncertainties) < 5:
                        snapshot.uncertainties.append({"code": "unavailable_artifact", "message": "An unavailable artifact reference was omitted."})
                    continue
                payload.update({"artifact_id": artifact_id, "file_name": resolved.file_name, "content_type": resolved.content_type, "size_bytes": resolved.size_bytes})
            counts[item.kind] = count + 1
            try:
                if item.kind == "scope": snapshot.focus = payload
                elif item.kind == "goal": snapshot.active_goal = payload
                elif item.kind == "recent_anchor": snapshot.recent_anchor = payload
                elif item.kind == "term_binding": snapshot.term_bindings.append(payload)
                elif item.kind == "artifact_ref": snapshot.artifacts.append(payload)
                elif item.kind == "open_loop": snapshot.open_loops.append(payload)
                elif item.kind == "decision": snapshot.decisions.append(payload)
                elif item.kind == "task_result_ref": snapshot.task_result_refs.append(payload)
            except ValueError:
                # Historical/invalid rows are never copied into a prompt.
                snapshot.uncertainties.append({"code": "invalid_context_item", "message": "An outdated context item was ignored."})
        # Readers do not take a write lock, so verify the revision after the
        # bounded projection. One retry prevents a mixed pre/post-write view
        # without holding locks while artifact ACL checks run.
        final_head = await repository.get_head(chat_id=chat_id, branch_id=branch_id)
        final_revision = final_head.revision if final_head else 0
        if final_revision != snapshot.revision and _attempt == 0:
            return await self.load_snapshot(
                chat_id=chat_id, branch_id=branch_id, owner_id=owner_id,
                tenant_id=tenant_id, _attempt=1,
            )
        if final_revision != snapshot.revision:
            snapshot.uncertainties.append({"code": "context_changed_during_read", "message": "Context changed; next turn will refresh it."})
        from app.core.prometheus_metrics import chat_context_snapshot_load_total
        chat_context_snapshot_load_total.labels(status="loaded").inc()
        return snapshot

    async def apply_outcome(
        self, *, projection: RuntimeOutcomeProjection, expected_revision: int, branch_id: str | None,
        owner_id: str, tenant_id: str, reducer,
    ) -> ChatContextApplyReceipt:
        repository = ChatContextRepository(self.session)
        revision = expected_revision
        # A model compaction can legitimately win the first CAS while a turn
        # outcome is being persisted.  Rebuild deterministic operations on the
        # new head when this turn is not older than that head; do not silently
        # drop the canonical runtime outcome in that benign race.
        for _ in range(3):
            operations = reducer.reduce(projection=projection, expected_revision=revision)
            # An artifact claim is durable only after a fresh registry
            # resolution.  A close is a lifecycle instruction and must not be
            # filtered through a lookup of the artifact it intentionally
            # removes.
            verified = await self._verified_artifact_operations(
                operations=operations, chat_id=projection.chat_id, owner_id=owner_id, tenant_id=tenant_id,
            )
            receipt = await ChatContextReconciler(repository).apply(
                chat_id=projection.chat_id, branch_id=branch_id, chat_turn_id=projection.chat_turn_id,
                expected_revision=revision, operations=self._with_expiry_policy(verified), tenant_id=tenant_id,
                project_keys=list(projection.project_context.get("explicit_project_keys") or []),
            )
            if "stale_revision" not in receipt.degradation_codes:
                break
            head = await repository.get_head(chat_id=projection.chat_id, branch_id=branch_id)
            if head is None or not await repository.can_rebase_turn(
                chat_id=projection.chat_id, chat_turn_id=projection.chat_turn_id,
                updated_through_turn_id=head.updated_through_turn_id,
            ):
                break
            revision = head.revision
        self._record_reconciliation(origin="deterministic", receipt=receipt)
        return receipt

    async def _verified_artifact_operations(
        self, *, operations: list[ChatContextOperation], chat_id: str, owner_id: str, tenant_id: str,
    ) -> list[ChatContextOperation]:
        """Keep only additions whose registry reference is still readable."""
        requested_artifact_ids = [
            operation.item_key for operation in operations
            if operation.kind == "artifact_ref" and operation.action not in {"close", "expire", "supersede"}
        ]
        resolved = await ChatArtifactReferenceService(self.session).resolve_many(
            artifact_ids=requested_artifact_ids, chat_id=chat_id,
            owner_id=owner_id, tenant_id=tenant_id,
        ) if requested_artifact_ids else {}
        return [
            operation for operation in operations
            if operation.kind != "artifact_ref"
            or operation.action in {"close", "expire", "supersede"}
            or operation.item_key in resolved
        ]

    async def apply_compaction(
        self, *, chat_id: str, branch_id: str | None, chat_turn_id: str,
        expected_revision: int, operations: list[ChatContextOperation], tenant_id: str | None = None,
    ) -> ChatContextApplyReceipt:
        """Persist only already-validated inferred operations in a worker transaction."""
        receipt = await ChatContextReconciler(ChatContextRepository(self.session)).apply(
            chat_id=chat_id, branch_id=branch_id, chat_turn_id=chat_turn_id,
            expected_revision=expected_revision, operations=self._with_expiry_policy(operations), tenant_id=tenant_id,
        )
        self._record_reconciliation(origin="compactor", receipt=receipt)
        return receipt

    async def cancel_turn_context(
        self, *, chat_id: str, chat_turn_id: str, branch_id: str | None = None,
    ) -> ChatContextApplyReceipt:
        """Close the conversational state owned by an explicitly cancelled turn.

        A pause/resume lifecycle reuses one ``chat_turn_id``.  Cancellation
        must therefore retire its open loop, but it must not close a newer
        goal created by another turn in the same chat.
        """
        repository = ChatContextRepository(self.session)
        # Cancellation is a lifecycle writer.  A concurrent normal outcome
        # may advance the revision between the snapshot and CAS; retrying
        # makes the close deterministic without ever closing another turn's
        # goal.
        receipt = ChatContextApplyReceipt(revision=0)
        for _ in range(4):
            head = await repository.get_head(chat_id=chat_id, branch_id=branch_id)
            if head is None:
                break
            expected_revision = head.revision
            source = [f"turn:{chat_turn_id}"]
            active_items = await repository.active_items(chat_id=chat_id, branch_id=branch_id)
            operations = [
                ChatContextOperation(
                    action="close", kind="open_loop", item_key=item.item_key,
                    source_ids=source, expected_revision=expected_revision,
                )
                for item in active_items
                if item.kind == "open_loop" and str(item.source_turn_id or "") == chat_turn_id
            ]
            active_goal = await repository.active_item(
                chat_id=chat_id, branch_id=branch_id, kind="goal", item_key="active_goal",
            )
            if active_goal and str(active_goal.source_turn_id or "") == chat_turn_id:
                operations.append(ChatContextOperation(
                    action="close", kind="goal", item_key="active_goal",
                    source_ids=source, expected_revision=expected_revision,
                ))
            receipt = await ChatContextReconciler(repository).apply(
                chat_id=chat_id, branch_id=branch_id, chat_turn_id=chat_turn_id,
                expected_revision=expected_revision, operations=operations,
            )
            if "stale_revision" not in receipt.degradation_codes:
                break
        self._record_reconciliation(origin="cancel", receipt=receipt)
        return receipt

    async def reset_context(self, *, chat_id: str, branch_id: str | None = None) -> ChatContextApplyReceipt:
        """Close all active chat-local items without touching transcript or facts."""
        repository = ChatContextRepository(self.session)
        head = await repository.get_or_create_head(chat_id=chat_id, branch_id=branch_id)
        closed = 0
        for item in await repository.active_items(chat_id=chat_id, branch_id=branch_id):
            item.status = "closed"
            closed += 1
        # Reset is a revision fence even for an already empty scope, otherwise
        # an in-flight writer can resurrect a context after the user reset it.
        head.revision += 1
        head.updated_through_turn_id = None
        head.updated_through_turn_order += 1
        await repository.flush()
        receipt = ChatContextApplyReceipt(revision=head.revision, applied_count=closed)
        self._record_reconciliation(origin="reset", receipt=receipt)
        return receipt

    async def inspect_snapshot(self, *, chat_id: str, owner_id: str, tenant_id: str, branch_id: str | None = None) -> dict[str, Any]:
        """Return a user-safe inspection projection without internal source IDs."""
        snapshot = await self.load_snapshot(chat_id=chat_id, branch_id=branch_id, owner_id=owner_id, tenant_id=tenant_id)
        focus = snapshot.focus.model_dump() if snapshot.focus else {}
        goal = snapshot.active_goal.model_dump() if snapshot.active_goal else {}
        return {
            "revision": snapshot.revision,
            "focus": {key: focus.get(key) for key in ("project_keys", "topic", "entity_refs") if key in focus},
            "active_goal": {key: goal.get(key) for key in ("text", "status") if key in goal} or None,
            "term_bindings": [{key: item.model_dump().get(key) for key in ("term", "aliases") if key in item.model_dump()} for item in snapshot.term_bindings],
            "artifacts": [{key: item.model_dump().get(key) for key in ("file_name", "content_type", "size_bytes", "role") if key in item.model_dump()} for item in snapshot.artifacts],
            "open_loops": [{key: item.model_dump().get(key) for key in ("status", "reason_code", "user_message") if key in item.model_dump()} for item in snapshot.open_loops],
            "decisions": [{key: item.model_dump().get(key) for key in ("text", "constraint") if key in item.model_dump()} for item in snapshot.decisions],
            "recent_anchor": ({key: snapshot.recent_anchor.model_dump().get(key) for key in ("user_intent", "assistant_outcome", "terminal_state") if key in snapshot.recent_anchor.model_dump()} if snapshot.recent_anchor else None),
            "task_results": [{key: item.model_dump().get(key) for key in ("outcome", "safe_summary") if key in item.model_dump()} for item in snapshot.task_result_refs],
        }

    async def expire_due_items(self, *, limit: int = 500) -> int:
        return await ChatContextRepository(self.session).expire_due_items(limit=max(1, min(limit, 1000)))

    @staticmethod
    def _with_expiry_policy(operations: list[ChatContextOperation]) -> list[ChatContextOperation]:
        settings = get_settings()
        ttl_days = {
            "term_binding": settings.CHAT_CONTEXT_TERM_BINDING_TTL_DAYS,
            "task_result_ref": settings.CHAT_CONTEXT_TASK_RESULT_TTL_DAYS,
            "open_loop": settings.CHAT_CONTEXT_BLOCKED_LOOP_TTL_DAYS,
        }
        now = datetime.now(timezone.utc)
        result: list[ChatContextOperation] = []
        for operation in operations:
            if operation.expires_at or operation.kind not in ttl_days:
                result.append(operation)
                continue
            if operation.kind == "open_loop" and operation.payload.get("status") != "blocked":
                result.append(operation)
                continue
            result.append(operation.model_copy(update={"expires_at": (now + timedelta(days=ttl_days[operation.kind])).isoformat()}))
        return result

    @staticmethod
    def _record_reconciliation(*, origin: str, receipt: ChatContextApplyReceipt) -> None:
        from app.core.prometheus_metrics import record_chat_context_reconciliation
        outcome = "stale" if "stale_revision" in receipt.degradation_codes else "applied" if receipt.applied_count else "no_op"
        record_chat_context_reconciliation(origin=origin, outcome=outcome)
