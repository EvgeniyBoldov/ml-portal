"""
Policy Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy


class PolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, policy: Policy) -> Policy:
        self.session.add(policy)
        await self.session.flush()
        await self.session.refresh(policy)
        return policy

    async def get_by_id(self, policy_id: UUID) -> Optional[Policy]:
        stmt = select(Policy).where(Policy.id == policy_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Policy]:
        stmt = select(Policy).where(Policy.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, policy: Policy) -> Policy:
        self.session.add(policy)
        await self.session.flush()
        await self.session.refresh(policy)
        return policy

    async def delete(self, policy: Policy) -> None:
        await self.session.delete(policy)
        await self.session.flush()

    async def list_policies(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Policy], int]:
        """List policies with filters"""
        stmt = select(Policy)
        
        if is_active is not None:
            stmt = stmt.where(Policy.is_active == is_active)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(Policy.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_default(self) -> Optional[Policy]:
        """Get the default policy"""
        return await self.get_by_slug("default")
