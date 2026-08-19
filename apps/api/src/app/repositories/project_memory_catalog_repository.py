"""Read models for the user-facing project-memory catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactScope, FactStatus
from app.models.project import Project


VISIBLE_PROJECT_MEMORY_STATUSES = (
    FactStatus.CONFIRMED.value,
    FactStatus.PENDING.value,
    FactStatus.UNCONFIRMED.value,
)


@dataclass(frozen=True)
class ProjectMemoryProjectRecord:
    id: UUID
    key: str
    name: str
    aliases: tuple[str, ...]
    status_counts: dict[str, int]
    updated_at: datetime | None


@dataclass(frozen=True)
class ProjectMemoryFactRecord:
    subject: str
    value: str
    kind: str
    status: str
    observed_at: datetime


class ProjectMemoryCatalogRepository:
    """Queries safe current fact projections for a tenant catalogue."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_projects(self, *, tenant_id: UUID) -> list[ProjectMemoryProjectRecord]:
        fact_rows = await self._session.execute(
            select(
                Fact.project_id,
                Fact.status,
                func.count(Fact.id),
                func.max(Fact.observed_at),
            )
            .where(
                Fact.tenant_id == tenant_id,
                Fact.scope == FactScope.PROJECT.value,
                Fact.project_id.is_not(None),
                Fact.superseded_by.is_(None),
                Fact.status.in_(VISIBLE_PROJECT_MEMORY_STATUSES),
            )
            .group_by(Fact.project_id, Fact.status)
        )
        grouped: dict[UUID, dict[str, object]] = {}
        for project_id, status, count, updated_at in fact_rows.all():
            if project_id is None:
                continue
            bucket = grouped.setdefault(
                project_id,
                {"status_counts": {}, "updated_at": None},
            )
            status_counts = bucket["status_counts"]
            if isinstance(status_counts, dict):
                status_counts[str(status)] = int(count)
            previous_updated_at = bucket["updated_at"]
            if isinstance(updated_at, datetime) and (
                previous_updated_at is None or updated_at > previous_updated_at
            ):
                bucket["updated_at"] = updated_at

        if not grouped:
            return []

        project_rows = await self._session.execute(
            select(Project)
            .where(Project.id.in_(grouped), Project.is_active.is_(True))
            .order_by(Project.name)
        )
        records: list[ProjectMemoryProjectRecord] = []
        for project in project_rows.scalars().all():
            aggregate = grouped[project.id]
            status_counts = aggregate["status_counts"]
            records.append(
                ProjectMemoryProjectRecord(
                    id=project.id,
                    key=project.key,
                    name=project.name,
                    aliases=tuple(project.aliases or ()),
                    status_counts=dict(status_counts) if isinstance(status_counts, dict) else {},
                    updated_at=aggregate["updated_at"] if isinstance(aggregate["updated_at"], datetime) else None,
                )
            )
        return records

    async def list_project_facts(
        self,
        *,
        tenant_id: UUID,
        project_key: str,
    ) -> tuple[ProjectMemoryProjectRecord, list[ProjectMemoryFactRecord]] | None:
        project = (
            await self._session.execute(
                select(Project).where(
                    Project.key == project_key,
                    Project.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if project is None:
            return None

        fact_rows = await self._session.execute(
            select(Fact)
            .where(
                Fact.tenant_id == tenant_id,
                Fact.project_id == project.id,
                Fact.scope == FactScope.PROJECT.value,
                Fact.superseded_by.is_(None),
                Fact.status.in_(VISIBLE_PROJECT_MEMORY_STATUSES),
            )
            .order_by(Fact.subject, Fact.observed_at.desc())
        )
        facts = [
            ProjectMemoryFactRecord(
                subject=fact.subject,
                value=fact.value,
                kind=fact.kind or "fact",
                status=fact.status,
                observed_at=fact.observed_at,
            )
            for fact in fact_rows.scalars().all()
        ]
        if not facts:
            return None

        counts = {status: 0 for status in VISIBLE_PROJECT_MEMORY_STATUSES}
        for fact in facts:
            counts[fact.status] += 1
        return (
            ProjectMemoryProjectRecord(
                id=project.id,
                key=project.key,
                name=project.name,
                aliases=tuple(project.aliases or ()),
                status_counts={status: count for status, count in counts.items() if count},
                updated_at=max(fact.observed_at for fact in facts),
            ),
            facts,
        )
