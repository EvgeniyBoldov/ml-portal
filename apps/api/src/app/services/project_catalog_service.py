"""Read canonical project names and aliases for runtime lookup."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_projects(self, *, limit: int | None = None) -> list[dict[str, object]]:
        statement = select(Project).where(Project.is_active.is_(True)).order_by(Project.name)
        if limit is not None:
            statement = statement.limit(limit)
        rows = await self._session.execute(statement)
        return [
            {"id": item.id, "key": item.key, "name": item.name, "aliases": list(item.aliases or [])}
            for item in rows.scalars().all()
        ]
