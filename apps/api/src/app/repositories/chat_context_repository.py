"""Persistence-only access for revisioned chat context."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_context_head import ChatContextHead
from app.models.chat_memory import ChatMemoryItem


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

    async def active_item(self, *, chat_id: str | uuid.UUID, branch_id: str | uuid.UUID | None, kind: str, item_key: str) -> Optional[ChatMemoryItem]:
        stmt = self._scope(select(ChatMemoryItem), chat_id=chat_id, branch_id=branch_id).where(
            ChatMemoryItem.kind == kind, ChatMemoryItem.item_key == item_key, ChatMemoryItem.status == "active",
        )
        return await self._session.scalar(stmt)

    async def flush(self) -> None:
        await self._session.flush()

    def add_item(self, item: ChatMemoryItem) -> None:
        self._session.add(item)

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
