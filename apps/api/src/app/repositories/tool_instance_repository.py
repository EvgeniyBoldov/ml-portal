"""
ToolInstance Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_instance import ToolInstance, InstanceScope


class ToolInstanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, instance: ToolInstance) -> ToolInstance:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, instance_id: UUID) -> Optional[ToolInstance]:
        stmt = select(ToolInstance).where(ToolInstance.id == instance_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[ToolInstance]:
        stmt = select(ToolInstance).where(ToolInstance.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, instance: ToolInstance) -> ToolInstance:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ToolInstance) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        tool_id: Optional[UUID] = None,
        scope: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        stmt = select(ToolInstance)
        
        if tool_id:
            stmt = stmt.where(ToolInstance.tool_id == tool_id)
        if scope:
            stmt = stmt.where(ToolInstance.scope == scope)
        if tenant_id:
            stmt = stmt.where(ToolInstance.tenant_id == tenant_id)
        if is_active is not None:
            stmt = stmt.where(ToolInstance.is_active == is_active)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(ToolInstance.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_for_tool(
        self,
        tool_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> List[ToolInstance]:
        """
        Get all instances for a tool, filtered by scope hierarchy.
        Returns instances available for the given user/tenant context.
        """
        conditions = [
            ToolInstance.tool_id == tool_id,
            ToolInstance.is_active == True,
        ]
        
        scope_conditions = [ToolInstance.scope == InstanceScope.DEFAULT.value]
        
        if tenant_id:
            scope_conditions.append(
                and_(
                    ToolInstance.scope == InstanceScope.TENANT.value,
                    ToolInstance.tenant_id == tenant_id
                )
            )
        
        if user_id and tenant_id:
            scope_conditions.append(
                and_(
                    ToolInstance.scope == InstanceScope.USER.value,
                    ToolInstance.user_id == user_id,
                    ToolInstance.tenant_id == tenant_id
                )
            )
        
        from sqlalchemy import or_
        conditions.append(or_(*scope_conditions))
        
        stmt = select(ToolInstance).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_default_for_tool(
        self,
        tool_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ToolInstance]:
        """
        Get the default instance for a tool following priority:
        User (is_default) > Tenant (is_default) > Default (is_default) > 
        User (any) > Tenant (any) > Default (any)
        """
        instances = await self.get_for_tool(tool_id, user_id, tenant_id)
        
        if not instances:
            return None
        
        def sort_key(inst: ToolInstance) -> tuple:
            scope_priority = {
                InstanceScope.USER.value: 0,
                InstanceScope.TENANT.value: 1,
                InstanceScope.DEFAULT.value: 2,
            }
            return (
                0 if inst.is_default else 1,
                scope_priority.get(inst.scope, 3),
                inst.created_at,
            )
        
        instances.sort(key=sort_key)
        return instances[0]

    async def get_by_tool_slug(
        self,
        tool_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ToolInstance]:
        """
        Get default instance for a tool by tool slug.
        """
        from app.models.tool import Tool
        
        tool_stmt = select(Tool.id).where(Tool.slug == tool_slug)
        tool_result = await self.session.execute(tool_stmt)
        tool_id = tool_result.scalar_one_or_none()
        
        if not tool_id:
            return None
        
        return await self.get_default_for_tool(tool_id, user_id, tenant_id)

    async def update_health_status(
        self,
        instance_id: UUID,
        status: str,
        error: Optional[str] = None,
    ) -> Optional[ToolInstance]:
        """Update health check status"""
        from datetime import datetime, timezone
        
        instance = await self.get_by_id(instance_id)
        if not instance:
            return None
        
        instance.health_status = status
        instance.last_health_check_at = datetime.now(timezone.utc)
        instance.health_check_error = error
        
        return await self.update(instance)
