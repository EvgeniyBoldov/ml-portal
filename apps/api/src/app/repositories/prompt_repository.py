from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.prompt import Prompt, PromptVersion, PromptStatus


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


class PromptVersionRepository:
    """Repository for PromptVersion operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, version: PromptVersion) -> PromptVersion:
        """Create new prompt version"""
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: UUID) -> Optional[PromptVersion]:
        """Get version by ID"""
        stmt = select(PromptVersion).where(PromptVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_prompt_and_version(
        self, 
        prompt_id: UUID, 
        version: int
    ) -> Optional[PromptVersion]:
        """Get specific version of a prompt"""
        stmt = select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version == version
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_prompt(self, prompt_id: UUID) -> Optional[PromptVersion]:
        """Get active version of a prompt"""
        stmt = select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.status == PromptStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_prompt(self, prompt_id: UUID) -> Optional[PromptVersion]:
        """Get latest version of a prompt (any status)"""
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt_id)
            .order_by(desc(PromptVersion.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_prompt(self, prompt_id: UUID) -> List[PromptVersion]:
        """Get all versions of a prompt ordered by version desc"""
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt_id)
            .order_by(desc(PromptVersion.version))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, prompt_id: UUID) -> int:
        """Get next version number for a prompt"""
        stmt = select(func.max(PromptVersion.version)).where(
            PromptVersion.prompt_id == prompt_id
        )
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def update_status(self, version_id: UUID, status: str) -> None:
        """Update version status"""
        stmt = (
            update(PromptVersion)
            .where(PromptVersion.id == version_id)
            .values(status=status)
        )
        await self.session.execute(stmt)

    async def archive_active_version(self, prompt_id: UUID) -> None:
        """Archive currently active version of a prompt"""
        stmt = (
            update(PromptVersion)
            .where(
                PromptVersion.prompt_id == prompt_id,
                PromptVersion.status == PromptStatus.ACTIVE.value
            )
            .values(status=PromptStatus.ARCHIVED.value)
        )
        await self.session.execute(stmt)

    async def update(self, version: PromptVersion, data: Dict[str, Any]) -> PromptVersion:
        """Update version fields"""
        for key, value in data.items():
            if hasattr(version, key) and value is not None:
                setattr(version, key, value)
        await self.session.flush()
        return version

    async def has_draft(self, prompt_id: UUID) -> bool:
        """Check if prompt has a draft version"""
        stmt = select(func.count()).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.status == PromptStatus.DRAFT.value
        )
        count = await self.session.scalar(stmt)
        return count > 0
