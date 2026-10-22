#ПРОВЕРЕНО
"""
Tenants repository for tenant management
"""
from __future__ import annotations

from app.core.logging import get_logger
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
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

    async def get_platform_default(self) -> Optional[Tenants]:
        result = await self.session.execute(
            select(Tenants).where(Tenants.is_platform_default.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100) -> List[Tenants]:
        """List all tenants"""
        result = await self.session.execute(
            select(Tenants).order_by(Tenants.name).limit(limit)
        )
        return result.scalars().all()

    async def list_page(
        self,
        *,
        page: int,
        size: int,
        search: str | None = None,
        is_active: bool | None = None,
        include_deprecated: bool = False,
    ) -> tuple[List[Tenants], int]:
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(Tenants.name.ilike(term), Tenants.description.ilike(term)))
        if is_active is not None:
            filters.append(Tenants.is_active.is_(is_active))
        if not include_deprecated:
            filters.append(Tenants.lifecycle_status != "deprecated")

        count_result = await self.session.execute(
            select(func.count()).select_from(Tenants).where(*filters)
        )
        total = int(count_result.scalar_one())
        page_result = await self.session.execute(
            select(Tenants)
            .where(*filters)
            .order_by(Tenants.name, Tenants.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return page_result.scalars().all(), total

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
        # The service only passes explicitly supplied fields; None clears nullable columns.
        update_data = kwargs

        if not update_data:
            return await self.get_by_id(tenant_id)

        await self.session.execute(
            update(Tenants)
            .where(Tenants.id == tenant_id)
            .values(**update_data)
        )

        return await self.get_by_id(tenant_id)

    async def set_platform_default(self, tenant_id: uuid.UUID) -> Optional[Tenants]:
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        await self.session.execute(update(Tenants).values(is_platform_default=False))
        await self.session.execute(
            update(Tenants)
            .where(Tenants.id == tenant_id)
            .values(is_platform_default=True)
        )
        await self.session.flush()
        return await self.get_by_id(tenant_id)

    async def get_tenants_by_model(self, model: str) -> List[Tenants]:
        """Get tenants using a specific model as embedding"""
        result = await self.session.execute(
            select(Tenants).where(Tenants.embedding_model_alias == model)
        )
        return result.scalars().all()
