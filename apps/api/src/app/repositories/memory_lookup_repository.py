"""Read queries backing the bounded runtime memory discovery tools."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryScope, GlossaryStatus
from app.models.memory import Fact, FactScope, FactStatus
from app.models.project import Project


class MemoryLookupRepository:
    """Database boundary for glossary, project catalogue, and project facts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible_glossary(
        self, *, user_id: UUID, tenant_id: UUID, limit: int,
    ) -> list[GlossaryEntry]:
        result = await self._session.execute(
            select(GlossaryEntry)
            .where(
                GlossaryEntry.is_active.is_(True),
                GlossaryEntry.status == GlossaryStatus.CONFIRMED.value,
                or_(
                    GlossaryEntry.scope == GlossaryScope.GLOBAL.value,
                    (GlossaryEntry.scope == GlossaryScope.TENANT.value)
                    & (GlossaryEntry.tenant_id == tenant_id),
                    (GlossaryEntry.scope == GlossaryScope.USER.value)
                    & (GlossaryEntry.user_id == user_id),
                ),
            )
            .order_by(GlossaryEntry.canonical_term)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active_projects(self, *, limit: int) -> list[Project]:
        result = await self._session.execute(
            select(Project).where(Project.is_active.is_(True)).order_by(Project.name).limit(limit)
        )
        return list(result.scalars().all())

    async def list_project_facts(
        self, *, tenant_id: UUID, project_ids: Sequence[UUID], limit: int,
    ) -> list[Fact]:
        if not project_ids:
            return []
        result = await self._session.execute(
            select(Fact)
            .where(
                Fact.tenant_id == tenant_id,
                Fact.project_id.in_(project_ids),
                Fact.scope == FactScope.PROJECT.value,
                Fact.status == FactStatus.CONFIRMED.value,
                Fact.superseded_by.is_(None),
            )
            .order_by(Fact.project_id, Fact.subject, Fact.observed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def read_project_facts(
        self, *, tenant_id: UUID, project_key: str, keys: Sequence[str], limit: int,
    ) -> tuple[Project | None, list[Fact]]:
        project_result = await self._session.execute(
            select(Project).where(Project.key == project_key, Project.is_active.is_(True))
        )
        project = project_result.scalar_one_or_none()
        if project is None:
            return None, []
        fact_result = await self._session.execute(
            select(Fact)
            .where(
                Fact.tenant_id == tenant_id,
                Fact.project_id == project.id,
                Fact.scope == FactScope.PROJECT.value,
                Fact.status == FactStatus.CONFIRMED.value,
                Fact.superseded_by.is_(None),
                Fact.subject.in_(keys),
            )
            .order_by(Fact.subject, Fact.observed_at.desc())
            .limit(limit)
        )
        return project, list(fact_result.scalars().all())
