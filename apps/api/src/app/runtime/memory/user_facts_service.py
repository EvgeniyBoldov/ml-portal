"""Hierarchical long-term facts services (user / tenant / platform).

Chat-scoped facts are intentionally excluded from this layer.
They can remain in a separate short-lived memory path.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Optional, Sequence
from uuid import UUID

from app.models.memory import FactScope
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.fact_store import FactStore


class BaseLongTermFactsService(ABC):
    """Base scope-specific facts service used by runtime memory."""

    def __init__(self, *, fact_store: FactStore) -> None:
        self._fact_store = fact_store

    @abstractmethod
    async def load_for_runtime(self, *, limit: int) -> list[FactDTO]:
        """Load scope-specific facts for runtime context."""

    @abstractmethod
    async def save_for_runtime(self, *, facts: Sequence[FactDTO]) -> int:
        """Persist facts that belong to this service's scope."""


class UserFactsService(BaseLongTermFactsService):
    """Read/write USER-scoped facts."""

    def __init__(
        self,
        *,
        fact_store: FactStore,
        user_id: Optional[UUID],
    ) -> None:
        super().__init__(fact_store=fact_store)
        self._user_id = user_id

    async def load_for_runtime(self, *, limit: int) -> list[FactDTO]:
        if self._user_id is None:
            return []
        return await self._fact_store.retrieve(
            scopes=[FactScope.USER],
            user_id=self._user_id,
            limit=limit,
        )

    async def save_for_runtime(self, *, facts: Sequence[FactDTO]) -> int:
        if self._user_id is None:
            return 0
        saved = 0
        for fact in facts:
            if fact.scope != FactScope.USER:
                continue
            normalized = fact
            if fact.user_id is None:
                normalized = replace(fact, user_id=self._user_id)
            await self._fact_store.upsert_with_supersede(normalized)
            saved += 1
        return saved


class TenantFactsService(BaseLongTermFactsService):
    """Read/write TENANT-scoped facts for current tenant."""

    def __init__(
        self,
        *,
        fact_store: FactStore,
        tenant_id: Optional[UUID],
    ) -> None:
        super().__init__(fact_store=fact_store)
        self._tenant_id = tenant_id

    async def load_for_runtime(self, *, limit: int) -> list[FactDTO]:
        if self._tenant_id is None:
            return []
        return await self._fact_store.retrieve(
            scopes=[FactScope.TENANT],
            tenant_id=self._tenant_id,
            limit=limit,
        )

    async def save_for_runtime(self, *, facts: Sequence[FactDTO]) -> int:
        if self._tenant_id is None:
            return 0
        saved = 0
        for fact in facts:
            if fact.scope != FactScope.TENANT or fact.tenant_id is None:
                continue
            await self._fact_store.upsert_with_supersede(fact)
            saved += 1
        return saved


class PlatformFactsService(BaseLongTermFactsService):
    """Read/write platform-scoped facts (TENANT scope with NULL tenant_id)."""

    async def load_for_runtime(self, *, limit: int) -> list[FactDTO]:
        return await self._fact_store.retrieve(
            scopes=[FactScope.TENANT],
            tenant_id=None,
            limit=limit,
        )

    async def save_for_runtime(self, *, facts: Sequence[FactDTO]) -> int:
        saved = 0
        for fact in facts:
            if fact.scope != FactScope.TENANT or fact.tenant_id is not None:
                continue
            await self._fact_store.upsert_with_supersede(fact)
            saved += 1
        return saved


class LongTermFactsService:
    """Facade over level services: user + tenant + platform."""

    def __init__(
        self,
        *,
        fact_store: FactStore,
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
    ) -> None:
        self._services: tuple[BaseLongTermFactsService, ...] = (
            UserFactsService(fact_store=fact_store, user_id=user_id),
            TenantFactsService(fact_store=fact_store, tenant_id=tenant_id),
            PlatformFactsService(fact_store=fact_store),
        )

    async def load_for_runtime(self, *, limit: int) -> list[FactDTO]:
        merged: list[FactDTO] = []
        seen_ids = set()
        for service in self._services:
            items = await service.load_for_runtime(limit=limit)
            for fact in items:
                if fact.id in seen_ids:
                    continue
                seen_ids.add(fact.id)
                merged.append(fact)
        merged.sort(key=lambda item: item.observed_at, reverse=True)
        return merged[:limit]

    async def save_for_runtime(self, *, facts: Sequence[FactDTO]) -> int:
        saved = 0
        for service in self._services:
            saved += await service.save_for_runtime(facts=facts)
        return saved

