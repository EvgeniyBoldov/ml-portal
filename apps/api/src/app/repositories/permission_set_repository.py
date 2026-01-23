"""
PermissionSet Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission_set import PermissionSet, PermissionScope


class PermissionSetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, perm_set: PermissionSet) -> PermissionSet:
        self.session.add(perm_set)
        await self.session.flush()
        await self.session.refresh(perm_set)
        return perm_set

    async def get_by_id(self, perm_id: UUID) -> Optional[PermissionSet]:
        stmt = select(PermissionSet).where(PermissionSet.id == perm_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, perm_set: PermissionSet) -> PermissionSet:
        self.session.add(perm_set)
        await self.session.flush()
        await self.session.refresh(perm_set)
        return perm_set

    async def delete(self, perm_set: PermissionSet) -> None:
        await self.session.delete(perm_set)
        await self.session.flush()

    async def list_permission_sets(
        self,
        skip: int = 0,
        limit: int = 100,
        scope: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Tuple[List[PermissionSet], int]:
        """List permission sets with filters"""
        stmt = select(PermissionSet)
        
        if scope:
            stmt = stmt.where(PermissionSet.scope == scope)
        if tenant_id:
            stmt = stmt.where(PermissionSet.tenant_id == tenant_id)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(PermissionSet.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_default(self) -> Optional[PermissionSet]:
        """Get the default (global) permission set"""
        stmt = select(PermissionSet).where(
            PermissionSet.scope == PermissionScope.DEFAULT.value
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: UUID) -> Optional[PermissionSet]:
        """Get permission set for a specific tenant"""
        stmt = select(PermissionSet).where(
            and_(
                PermissionSet.scope == PermissionScope.TENANT.value,
                PermissionSet.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> Optional[PermissionSet]:
        """Get permission set for a specific user in a tenant"""
        stmt = select(PermissionSet).where(
            and_(
                PermissionSet.scope == PermissionScope.USER.value,
                PermissionSet.user_id == user_id,
                PermissionSet.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_context(
        self,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> List[PermissionSet]:
        """
        Get all permission sets applicable to a user/tenant context.
        Returns: [default, tenant (if exists), user (if exists)]
        """
        result = []
        
        default_perm = await self.get_default()
        if default_perm:
            result.append(default_perm)
        
        if tenant_id:
            tenant_perm = await self.get_for_tenant(tenant_id)
            if tenant_perm:
                result.append(tenant_perm)
        
        if user_id and tenant_id:
            user_perm = await self.get_for_user(user_id, tenant_id)
            if user_perm:
                result.append(user_perm)
        
        return result

    async def get_or_create_default(self) -> PermissionSet:
        """Get or create the default permission set"""
        default_perm = await self.get_default()
        if default_perm:
            return default_perm
        
        default_perm = PermissionSet(
            scope=PermissionScope.DEFAULT.value,
            allowed_tools=[],
            denied_tools=[],
            allowed_collections=[],
            denied_collections=[],
        )
        return await self.create(default_perm)

    async def get_or_create_for_tenant(self, tenant_id: UUID) -> PermissionSet:
        """Get or create permission set for a tenant"""
        tenant_perm = await self.get_for_tenant(tenant_id)
        if tenant_perm:
            return tenant_perm
        
        tenant_perm = PermissionSet(
            scope=PermissionScope.TENANT.value,
            tenant_id=tenant_id,
            allowed_tools=[],
            denied_tools=[],
            allowed_collections=[],
            denied_collections=[],
        )
        return await self.create(tenant_perm)

    async def get_or_create_for_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> PermissionSet:
        """Get or create permission set for a user"""
        user_perm = await self.get_for_user(user_id, tenant_id)
        if user_perm:
            return user_perm
        
        user_perm = PermissionSet(
            scope=PermissionScope.USER.value,
            user_id=user_id,
            tenant_id=tenant_id,
            allowed_tools=[],
            denied_tools=[],
            allowed_collections=[],
            denied_collections=[],
        )
        return await self.create(user_perm)
