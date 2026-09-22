"""Persistence-only access for revisioned chat context."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_context_head import ChatContextHead
from app.models.chat_memory import ChatMemoryItem
from app.models.chat_turn import ChatTurn
from app.models.chat import ChatMessages
from app.models.chat_artifact_reference import ChatArtifactReference
from app.models.glossary import GlossaryEntry
from app.models.runtime_plan import RuntimePlan, RuntimePlanTask
from app.models.project import Project
from app.runtime.entity_ids import runtime_task_id


class ChatContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _uuid(value: str | uuid.UUID | None) -> Optional[uuid.UUID]:
        return uuid.UUID(str(value)) if value else None

    def _scope(self, stmt, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None):
        branch = self._uuid(branch_id)
        return stmt.where(
            ChatMemoryItem.chat_id == uuid.UUID(str(chat_id)),
            ChatMemoryItem.sandbox_branch_id == branch if branch else ChatMemoryItem.sandbox_branch_id.is_(None),
        )

    async def get_head(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None, lock: bool = False) -> Optional[ChatContextHead]:
        branch = self._uuid(branch_id)
        stmt = select(ChatContextHead).where(
            ChatContextHead.chat_id == uuid.UUID(str(chat_id)),
            ChatContextHead.sandbox_branch_id == branch if branch else ChatContextHead.sandbox_branch_id.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self._session.scalar(stmt)

    async def get_or_create_head(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None) -> ChatContextHead:
        head = await self.get_head(chat_id=chat_id, branch_id=branch_id, lock=True)
        if head:
            return head
        head = ChatContextHead(chat_id=uuid.UUID(str(chat_id)), sandbox_branch_id=self._uuid(branch_id))
        try:
            # A row lock cannot protect a scope whose head does not exist yet.
            # The partial uniqueness constraint is the final arbiter; a nested
            # transaction lets the loser reload the winner without aborting the
            # enclosing runtime transaction.
            async with self._session.begin_nested():
                self._session.add(head)
                await self._session.flush()
            return head
        except IntegrityError:
            winner = await self.get_head(chat_id=chat_id, branch_id=branch_id, lock=True)
            if winner is None:  # defensive: preserve the real database error
                raise
            return winner

    async def active_items(
        self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None,
        limit: int | None = None,
    ) -> list[ChatMemoryItem]:
        now = datetime.now(timezone.utc)
        stmt = self._scope(select(ChatMemoryItem), chat_id=chat_id, branch_id=branch_id).where(
            ChatMemoryItem.status == "active",
            (ChatMemoryItem.expires_at.is_(None)) | (ChatMemoryItem.expires_at > now),
        ).order_by(ChatMemoryItem.updated_at.desc())
        if limit is not None:
            stmt = stmt.limit(max(1, min(limit, 300)))
        return list((await self._session.execute(stmt)).scalars().all())

    async def active_items_by_kind(
        self,
        *,
        chat_id: str | uuid.UUID,
        branch_id: str | uuid.UUID | None,
        kind_limits: dict[str, int],
    ) -> list[ChatMemoryItem]:
        """Return a bounded projection for every requested kind.

        A global ``ORDER BY updated_at LIMIT N`` is deliberately not used here:
        a busy artifact collection must never evict singleton conversational
        state such as the current scope or active goal from a snapshot.
        Separate bounded statements also keep this portable and predictable
        without loading an unbounded context scope into application memory.
        """
        now = datetime.now(timezone.utc)
        result: list[ChatMemoryItem] = []
        for kind, raw_limit in kind_limits.items():
            limit = max(1, min(int(raw_limit), 100))
            stmt = self._scope(select(ChatMemoryItem), chat_id=chat_id, branch_id=branch_id).where(
                ChatMemoryItem.kind == kind,
                ChatMemoryItem.status == "active",
                (ChatMemoryItem.expires_at.is_(None)) | (ChatMemoryItem.expires_at > now),
            ).order_by(ChatMemoryItem.updated_at.desc()).limit(limit)
            result.extend((await self._session.execute(stmt)).scalars().all())
        return result

    async def active_item(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None, kind: str, item_key: str) -> Optional[ChatMemoryItem]:
        stmt = self._scope(select(ChatMemoryItem), chat_id=chat_id, branch_id=branch_id).where(
            ChatMemoryItem.kind == kind, ChatMemoryItem.item_key == item_key, ChatMemoryItem.status == "active",
        )
        return await self._session.scalar(stmt)

    async def flush(self) -> None:
        await self._session.flush()

    def add_item(self, item: ChatMemoryItem) -> None:
        self._session.add(item)

    async def validate_provenance(
        self, *, chat_id: str, chat_turn_id: str, source_ids: list[str],
        tenant_id: str | None = None,
        project_keys: list[str] | None = None,
        allow_missing_artifact_ids: set[str] | None = None,
        expected_task_refs: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Resolve typed provenance against the owning chat and runtime turn.

        Source strings are input to a persistence boundary, not trusted IDs.
        Every reference must therefore resolve inside the current chat/run
        scope before it can be copied to an indexed memory row.
        """
        chat_uuid = uuid.UUID(str(chat_id))
        turn_uuid = uuid.UUID(str(chat_turn_id))
        turn = await self._session.scalar(select(ChatTurn).where(
            ChatTurn.id == turn_uuid, ChatTurn.chat_id == chat_uuid,
        ))
        if turn is None:
            raise ValueError("chat turn is outside context chat")
        columns: dict[str, object] = {
            "source_turn_id": turn_uuid, "source_message_id": None, "source_run_id": None,
        }
        for source_id in source_ids:
            prefix, value = source_id.split(":", 1)
            if prefix == "turn":
                if uuid.UUID(value) != turn_uuid:
                    raise ValueError("operation cannot claim another chat turn")
            elif prefix == "message":
                message_id = uuid.UUID(value)
                present = await self._session.scalar(select(ChatMessages.id).where(
                    ChatMessages.id == message_id, ChatMessages.chat_id == chat_uuid,
                ))
                if present is None:
                    raise ValueError("message source is outside context chat")
                columns["source_message_id"] = message_id
            elif prefix == "run":
                run_id = uuid.UUID(value)
                if turn.runtime_run_id != run_id:
                    raise ValueError("run source is not bound to context turn")
                columns["source_run_id"] = run_id
            elif prefix == "artifact":
                artifact_id = uuid.UUID(value)
                present = await self._session.scalar(select(ChatArtifactReference.id).where(
                    ChatArtifactReference.id == artifact_id,
                    ChatArtifactReference.chat_id == chat_uuid,
                ))
                # A close is allowed to retire an already-persisted chat
                # reference after its registry row was deleted.  The caller
                # grants this narrow exception only after locating the active
                # item in this same chat/branch scope.
                if present is None and value not in (allow_missing_artifact_ids or set()):
                    raise ValueError("artifact source is outside context chat")
            elif prefix == "glossary":
                glossary_id = uuid.UUID(value)
                scope_clause = or_(
                    GlossaryEntry.scope == "global",
                    and_(GlossaryEntry.scope == "user", GlossaryEntry.user_id == turn.user_id),
                )
                if tenant_id:
                    tenant_uuid = uuid.UUID(str(tenant_id))
                    scope_clause = or_(
                        scope_clause,
                        and_(GlossaryEntry.scope == "tenant", GlossaryEntry.tenant_id == tenant_uuid),
                    )
                normalized_project_keys = [str(key).strip().casefold() for key in project_keys or [] if str(key).strip()]
                if normalized_project_keys:
                    scope_clause = or_(
                        scope_clause,
                        and_(
                            GlossaryEntry.scope == "project",
                            GlossaryEntry.project_id.in_(
                                select(Project.id).where(
                                    Project.is_active.is_(True),
                                    func.lower(Project.key).in_(normalized_project_keys),
                                )
                            ),
                        ),
                    )
                present = await self._session.scalar(select(GlossaryEntry.id).where(
                    GlossaryEntry.id == glossary_id, GlossaryEntry.is_active.is_(True),
                    scope_clause,
                ))
                if present is None:
                    raise ValueError("glossary source is unavailable")
            elif prefix == "task":
                # A context task source is the canonical UUID5 entity ID,
                # whereas RuntimePlanTask.task_id is the planner's local key.
                if turn.runtime_run_id is None:
                    raise ValueError("task source requires a runtime-bound turn")
                candidates = list((await self._session.execute(
                    select(RuntimePlan.id, RuntimePlanTask.task_id)
                    .join(RuntimePlan, RuntimePlan.id == RuntimePlanTask.plan_id)
                    .where(
                        RuntimePlan.root_run_id == turn.runtime_run_id,
                        RuntimePlan.chat_id == chat_uuid,
                    )
                )).all())
                matched_plan_id = next((
                    plan_id for plan_id, task_id in candidates
                    if runtime_task_id(str(plan_id), str(task_id)) == value
                ), None)
                if matched_plan_id is None:
                    raise ValueError("task source is outside context run")
                claimed_plan_id = (expected_task_refs or {}).get(value)
                if claimed_plan_id is not None and claimed_plan_id != str(matched_plan_id):
                    raise ValueError("task result claims another runtime plan")
            else:
                raise ValueError("unsupported context provenance source")
        return columns

    async def can_rebase_turn(
        self, *, chat_id: str, chat_turn_id: str, updated_through_turn_id: uuid.UUID | None,
    ) -> bool:
        """Whether a deterministic outcome remains newer than the head.

        A compactor may advance the revision for the same turn after the
        deterministic projection was assembled.  Rebuilding against that head
        is safe.  An older turn must never rebase over a newer user turn.
        """
        if updated_through_turn_id is None:
            return False
        current_id = uuid.UUID(str(chat_turn_id))
        if current_id == updated_through_turn_id:
            return True
        rows = list((await self._session.execute(
            select(ChatTurn.id, ChatTurn.started_at).where(
                ChatTurn.chat_id == uuid.UUID(str(chat_id)),
                ChatTurn.id.in_([current_id, updated_through_turn_id]),
            )
        )).all())
        timestamps = {row_id: started_at for row_id, started_at in rows}
        return (
            current_id in timestamps
            and updated_through_turn_id in timestamps
            and timestamps[current_id] > timestamps[updated_through_turn_id]
        )

    async def expire_due_items(self, *, limit: int) -> int:
        now = datetime.now(timezone.utc)
        items = list((await self._session.execute(
            select(ChatMemoryItem)
            .where(ChatMemoryItem.status == "active", ChatMemoryItem.expires_at.is_not(None), ChatMemoryItem.expires_at <= now)
            .order_by(ChatMemoryItem.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )).scalars().all())
        if not items:
            return 0
        heads: dict[tuple[uuid.UUID, uuid.UUID | None], ChatContextHead] = {}
        for item in items:
            scope = (item.chat_id, item.sandbox_branch_id)
            head = heads.get(scope)
            if head is None:
                head = await self.get_or_create_head(chat_id=item.chat_id, branch_id=item.sandbox_branch_id)
                heads[scope] = head
            item.status = "expired"
        for head in heads.values():
            head.revision += 1
            head.updated_through_turn_order += 1
        await self.flush()
        return len(items)
