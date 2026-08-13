"""Administrative CRUD for confirmed user and tenant memory facts."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactScope, FactSource, FactStatus
from app.repositories.fact_admin_repository import FactAdminRepository


class AdminFactNotFoundError(LookupError):
    pass


class FactAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = FactAdminRepository(session)
        self._session = session

    async def list(self, *, owner_type: str, owner_id: UUID) -> list[Fact]:
        return await self._repo.list_active(owner_type=owner_type, owner_id=owner_id)

    async def create(self, *, owner_type: str, owner_id: UUID, subject: str, value: str) -> Fact:
        now = datetime.now(timezone.utc)
        fact = Fact(
            id=uuid4(),
            tenant_id=owner_id if owner_type == "tenant" else None,
            owner_type=owner_type,
            owner_id=owner_id,
            scope=FactScope.USER.value if owner_type == "user" else FactScope.TENANT.value,
            subject=_subject(subject),
            value=_value(value),
            normalized_value=_normalized(value),
            confidence=1.0,
            source=FactSource.MANUAL.value,
            source_ref=f"admin:manual:{owner_type}:{owner_id}",
            observed_at=now,
            user_visible=owner_type == "user",
            status=FactStatus.CONFIRMED.value,
            support_count=1,
            first_confirmed_at=now,
            last_confirmed_at=now,
        )
        return await self._repo.add(fact)

    async def update(
        self,
        *,
        fact_id: UUID,
        owner_type: str,
        owner_id: UUID,
        subject: str,
        value: str,
    ) -> Fact:
        current = await self._repo.get_active(fact_id=fact_id, owner_type=owner_type, owner_id=owner_id)
        if current is None:
            raise AdminFactNotFoundError(fact_id)
        replacement = await self.create(owner_type=owner_type, owner_id=owner_id, subject=subject, value=value)
        replacement.revision = current.revision + 1
        await self._repo.supersede(fact_id=current.id, replacement_id=replacement.id)
        return replacement

    async def delete(self, *, fact_id: UUID, owner_type: str, owner_id: UUID) -> None:
        current = await self._repo.get_active(fact_id=fact_id, owner_type=owner_type, owner_id=owner_id)
        if current is None:
            raise AdminFactNotFoundError(fact_id)
        await self._repo.supersede(fact_id=current.id, replacement_id=current.id)


def _subject(value: str) -> str:
    return " ".join(value.strip().lower().split())[:200]


def _value(value: str) -> str:
    return value.strip()[:500]


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())[:500]

