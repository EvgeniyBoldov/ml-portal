from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt


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

    async def get_by_slug(self, slug: str, active_only: bool = True) -> Optional[Prompt]:
        """
        Get the latest version of a prompt by slug.
        """
        stmt = select(Prompt).where(Prompt.slug == slug)
        
        if active_only:
            stmt = stmt.where(Prompt.is_active == True)
            
        # Order by version desc to get latest
        stmt = stmt.order_by(desc(Prompt.version)).limit(1)
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_prompts(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None
    ) -> Tuple[List[Prompt], int]:
        """
        List latest versions of all prompts.
        """
        # Subquery to find max version for each slug
        subquery = (
            select(Prompt.slug, func.max(Prompt.version).label("max_version"))
            .group_by(Prompt.slug)
            .subquery()
        )

        stmt = (
            select(Prompt)
            .join(
                subquery,
                (Prompt.slug == subquery.c.slug) & 
                (Prompt.version == subquery.c.max_version)
            )
        )
        
        if type_filter:
            stmt = stmt.where(Prompt.type == type_filter)
            
        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0

        # Pagination
        stmt = stmt.order_by(Prompt.slug).offset(skip).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
