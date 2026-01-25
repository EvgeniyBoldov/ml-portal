from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt, PromptStatus


class PromptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, prompt: Prompt) -> Prompt:
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def get_by_id(self, prompt_id: UUID) -> Optional[Prompt]:
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug_and_version(self, slug: str, version: int) -> Optional[Prompt]:
        """Get specific version of a prompt."""
        stmt = select(Prompt).where(
            Prompt.slug == slug,
            Prompt.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_slug(self, slug: str) -> Optional[Prompt]:
        """Get the active version of a prompt by slug."""
        stmt = select(Prompt).where(
            Prompt.slug == slug,
            Prompt.status == PromptStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_slug(self, slug: str) -> Optional[Prompt]:
        """Get the latest version of a prompt by slug (any status)."""
        stmt = (
            select(Prompt)
            .where(Prompt.slug == slug)
            .order_by(desc(Prompt.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_versions(self, slug: str) -> List[Prompt]:
        """Get all versions of a prompt ordered by version desc."""
        stmt = (
            select(Prompt)
            .where(Prompt.slug == slug)
            .order_by(desc(Prompt.version))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, slug: str) -> int:
        """Get next version number for a slug."""
        stmt = select(func.max(Prompt.version)).where(Prompt.slug == slug)
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def update_status(self, prompt_id: UUID, status: str) -> None:
        """Update prompt status."""
        stmt = (
            update(Prompt)
            .where(Prompt.id == prompt_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def archive_active_version(self, slug: str) -> None:
        """Archive currently active version of a prompt."""
        stmt = (
            update(Prompt)
            .where(
                Prompt.slug == slug,
                Prompt.status == PromptStatus.ACTIVE.value
            )
            .values(status=PromptStatus.ARCHIVED.value)
        )
        await self.session.execute(stmt)

    async def list_prompts(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List prompts with aggregated version info.
        Returns list of dicts with slug, name, type, latest_version, active_version, versions_count.
        """
        # Get unique slugs with their info
        base_query = select(
            Prompt.slug,
            func.max(Prompt.name).label('name'),
            func.max(Prompt.description).label('description'),
            func.max(Prompt.type).label('type'),
            func.max(Prompt.version).label('latest_version'),
            func.count(Prompt.id).label('versions_count'),
            func.max(Prompt.updated_at).label('updated_at')
        ).group_by(Prompt.slug)
        
        if type_filter:
            base_query = base_query.where(Prompt.type == type_filter)
        
        # Count total unique slugs
        count_subq = base_query.subquery()
        count_stmt = select(func.count()).select_from(count_subq)
        total = await self.session.scalar(count_stmt) or 0
        
        # Get paginated results
        stmt = base_query.order_by(Prompt.slug).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        rows = result.all()
        
        # Get active versions for each slug
        slugs = [r.slug for r in rows]
        if slugs:
            active_stmt = select(Prompt.slug, Prompt.version).where(
                Prompt.slug.in_(slugs),
                Prompt.status == PromptStatus.ACTIVE.value
            )
            active_result = await self.session.execute(active_stmt)
            active_versions = {r.slug: r.version for r in active_result.all()}
        else:
            active_versions = {}
        
        items = []
        for row in rows:
            items.append({
                'slug': row.slug,
                'name': row.name,
                'description': row.description,
                'type': row.type,
                'latest_version': row.latest_version,
                'active_version': active_versions.get(row.slug),
                'versions_count': row.versions_count,
                'updated_at': row.updated_at
            })
        
        return items, total

    async def update(self, prompt: Prompt, data: Dict[str, Any]) -> Prompt:
        """Update prompt fields."""
        for key, value in data.items():
            if hasattr(prompt, key) and value is not None:
                setattr(prompt, key, value)
        await self.session.flush()
        return prompt
