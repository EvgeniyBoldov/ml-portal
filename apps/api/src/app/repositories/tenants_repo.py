#ПРОВЕРЕНО
"""
Tenants repository for tenant management
"""
from __future__ import annotations

from app.core.logging import get_logger
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from app.models.tenant import Tenants
import uuid




logger = get_logger(__name__)

class AsyncTenantsRepository:
    """Async repository for tenant operations"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, tenant_id: uuid.UUID) -> Optional[Tenants]:
        """Get tenant by ID"""
        result = await self.session.execute(
            select(Tenants).where(Tenants.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Tenants]:
        """Get tenant by name"""
        result = await self.session.execute(
            select(Tenants).where(Tenants.name == name)
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100) -> List[Tenants]:
        """List all tenants"""
        result = await self.session.execute(
            select(Tenants).order_by(Tenants.name).limit(limit)
        )
        return result.scalars().all()

    async def create(self, name: str, is_active: bool = True, **kwargs) -> Tenants:
        """Create a new tenant"""
        tenant = Tenants(
            id=uuid.uuid4(),
            name=name,
            is_active=is_active,
            **kwargs
        )
        self.session.add(tenant)
        await self.session.flush()
        await self.session.refresh(tenant)
        return tenant

    async def update(self, tenant_id: uuid.UUID, **kwargs) -> Optional[Tenants]:
        """Update tenant with any fields"""
        # Remove None values
        update_data = {k: v for k, v in kwargs.items() if v is not None}

        if not update_data:
            return await self.get_by_id(tenant_id)

        await self.session.execute(
            update(Tenants)
            .where(Tenants.id == tenant_id)
            .values(**update_data)
        )

        return await self.get_by_id(tenant_id)

    async def delete(self, tenant_id: uuid.UUID) -> bool:
        """Delete tenant"""
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return False

        await self.session.delete(tenant)
        await self.session.flush()
        return True

    async def get_tenants_by_model(self, model: str) -> List[Tenants]:
        """Get tenants using a specific model as embedding"""
        result = await self.session.execute(
            select(Tenants).where(Tenants.embedding_model_alias == model)
        )
        return result.scalars().all()
