"""Read-only projection of confirmed project memory for system tools."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactStatus
from app.models.project import Project


class ProjectMemoryService:
    """Resolve a project by its exact key and return a bounded safe view."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self,
        *,
        project_key: str,
        subject_prefix: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        key = project_key.strip().lower()
        project = (
            await self._session.execute(
                select(Project).where(Project.key == key, Project.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if project is None:
            return {"project": None, "facts": [], "count": 0}

        stmt = (
            select(Fact)
            .where(
                Fact.project_id == project.id,
                Fact.scope == "project",
                Fact.status == FactStatus.CONFIRMED.value,
                Fact.superseded_by.is_(None),
            )
            .order_by(Fact.observed_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        if subject_prefix:
            stmt = stmt.where(Fact.subject.like(f"{subject_prefix.strip().lower()}%"))
        rows = (await self._session.execute(stmt)).scalars().all()
        facts = [
            {
                "subject": row.subject,
                "value": row.value,
                "kind": row.kind or "fact",
                "confidence": row.confidence,
                "status": row.status,
            }
            for row in rows
        ]
        return {
            "project": {
                "key": project.key,
                "name": project.name,
                "aliases": list(project.aliases or []),
            },
            "facts": facts,
            "count": len(facts),
        }
