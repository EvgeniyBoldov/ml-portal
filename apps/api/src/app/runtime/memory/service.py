"""Canonical durable-memory read/write facade for runtime consumers."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Optional, Sequence
from uuid import UUID

from app.models.memory import FactScope
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.fact_store import FactStore

MAX_PROFILE_ITEMS = 12
MAX_PROFILE_CHARS = 2_400
MAX_PROFILE_ITEM_CHARS = 240


@dataclass(frozen=True)
class MemorySubject:
    scope: FactScope
    owner_type: str
    owner_id: UUID
    tenant_id: Optional[UUID] = None


@dataclass(frozen=True)
class MemorySnapshot:
    user_facts: tuple[FactDTO, ...] = ()
    tenant_facts: tuple[FactDTO, ...] = ()

    @property
    def entries(self) -> tuple[FactDTO, ...]:
        return self.user_facts + self.tenant_facts

    def planner_context(self, *, limit: int = MAX_PROFILE_ITEMS) -> list[dict[str, object]]:
        return _context(self.entries[:limit])

    def agent_context(self, *, query: str, limit: int = MAX_PROFILE_ITEMS) -> list[dict[str, object]]:
        terms = {word.lower() for word in query.split() if len(word) > 2}
        ranked = sorted(self.entries, key=lambda item: sum(term in f"{item.subject} {item.value}".lower() for term in terms), reverse=True)
        return _context(ranked[:limit])


class MemoryService:
    """The sole durable-memory facade; prompts and writers never query facts directly."""

    def __init__(self, *, fact_store: FactStore) -> None:
        self._facts = fact_store

    async def read_snapshot(self, *, user_id: Optional[UUID], tenant_id: Optional[UUID], limit: int) -> MemorySnapshot:
        user = await self._facts.retrieve(scopes=[FactScope.USER], owner_type="user", owner_id=user_id, limit=limit) if user_id else []
        tenant = await self._facts.retrieve(scopes=[FactScope.TENANT], owner_type="tenant", owner_id=tenant_id, limit=limit) if tenant_id else []
        return MemorySnapshot(user_facts=tuple(user), tenant_facts=tuple(tenant))

    async def write_extracted(self, *, facts: Sequence[FactDTO], user_id: Optional[UUID], tenant_id: Optional[UUID]) -> int:
        saved = 0
        for fact in facts:
            if fact.scope == FactScope.USER and user_id is not None:
                entry = replace(fact, tenant_id=tenant_id, owner_type="user", owner_id=user_id, kind=fact.kind or "fact")
            elif fact.scope == FactScope.TENANT and tenant_id is not None:
                entry = replace(fact, tenant_id=tenant_id, owner_type="tenant", owner_id=tenant_id, kind=fact.kind or "fact")
            else:
                continue
            await self._facts.upsert_with_supersede(entry)
            saved += 1
        return saved

    async def list_user_visible(self, *, user_id: UUID, limit: int, offset: int) -> list[FactDTO]:
        return await self._facts.list_user_visible(user_id=user_id, limit=limit, offset=offset)

    async def forget_user_entries(self, *, user_id: UUID, fact_ids: Sequence[UUID]) -> int:
        return await self._facts.forget_owned(owner_type="user", owner_id=user_id, fact_ids=fact_ids)

    async def reassign_tenant_context(self, *, from_tenant_id: UUID, to_tenant_id: UUID) -> int:
        return await self._facts.reassign_tenant_context(from_tenant_id=from_tenant_id, to_tenant_id=to_tenant_id)


def _context(facts: Sequence[FactDTO]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    used = 0
    for fact in facts:
        subject = fact.subject[:MAX_PROFILE_ITEM_CHARS]
        value = fact.value[:MAX_PROFILE_ITEM_CHARS]
        size = len(subject) + len(value)
        if used + size > MAX_PROFILE_CHARS:
            break
        entries.append({"scope": fact.scope.value, "kind": fact.kind, "subject": subject, "value": value, "confidence": fact.confidence})
        used += size
    return entries
