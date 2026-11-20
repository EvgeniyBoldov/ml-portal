from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt


class PromptRepository:
    """Repository for Prompt (container) operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, prompt: Prompt) -> Prompt:
        """Create new prompt container"""
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def get_by_id(self, prompt_id: UUID) -> Optional[Prompt]:
        """Get prompt container by ID"""
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Prompt]:
        """Get prompt container by slug"""
        stmt = select(Prompt).where(Prompt.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_prompts(
        self, 
        skip: int = 0, 
        limit: int = 100,
        type_filter: Optional[str] = None
    ) -> Tuple[List[Prompt], int]:
        """List prompt containers with pagination"""
        base_query = select(Prompt)
        
        if type_filter:
            base_query = base_query.where(Prompt.type == type_filter)
        
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        # Get paginated results
        stmt = base_query.order_by(Prompt.slug).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        
        return items, total

    async def update(self, prompt: Prompt, data: Dict[str, Any]) -> Prompt:
        """Update prompt container fields"""
        for key, value in data.items():
            if hasattr(prompt, key) and value is not None:
                setattr(prompt, key, value)
        await self.session.flush()
        return prompt

    async def delete(self, prompt_id: UUID) -> bool:
        """Delete prompt container (cascade deletes versions)"""
        prompt = await self.get_by_id(prompt_id)
        if not prompt:
            return False
        await self.session.delete(prompt)
        await self.session.flush()
        return True


