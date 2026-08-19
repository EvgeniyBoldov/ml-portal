"""User-facing read service for the Project Memory catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_memory_catalog_repository import (
    ProjectMemoryCatalogRepository,
)


@dataclass(frozen=True)
class ProjectMemoryProject:
    key: str
    name: str
    aliases: tuple[str, ...]
    status_counts: dict[str, int]
    updated_at: datetime | None


@dataclass(frozen=True)
class ProjectMemoryFact:
    subject: str
    value: str
    kind: str
    status: str
    observed_at: datetime


@dataclass(frozen=True)
class ProjectMemoryProjectDetail:
    project: ProjectMemoryProject
    facts: tuple[ProjectMemoryFact, ...]


class ProjectMemoryCatalogService:
    """Expose a bounded safe overview without changing runtime memory reads."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = ProjectMemoryCatalogRepository(session)

    async def list_projects(self, *, tenant_id: UUID) -> list[ProjectMemoryProject]:
        rows = await self._repository.list_projects(tenant_id=tenant_id)
        return [
            ProjectMemoryProject(
                key=row.key,
                name=row.name,
                aliases=row.aliases,
                status_counts=row.status_counts,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def get_project(self, *, tenant_id: UUID, project_key: str) -> ProjectMemoryProjectDetail | None:
        result = await self._repository.list_project_facts(
            tenant_id=tenant_id,
            project_key=project_key.strip().lower(),
        )
        if result is None:
            return None
        project, facts = result
        return ProjectMemoryProjectDetail(
            project=ProjectMemoryProject(
                key=project.key,
                name=project.name,
                aliases=project.aliases,
                status_counts=project.status_counts,
                updated_at=project.updated_at,
            ),
            facts=tuple(
                ProjectMemoryFact(
                    subject=fact.subject,
                    value=fact.value,
                    kind=fact.kind,
                    status=fact.status,
                    observed_at=fact.observed_at,
                )
                for fact in facts
            ),
        )
