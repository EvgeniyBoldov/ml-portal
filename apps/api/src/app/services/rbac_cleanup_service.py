from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import RbacRule


class RbacCleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def remove_rules_for_owner(
        self,
        *,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
    ) -> int:
        if owner_user_id is None and owner_tenant_id is None:
            return 0

        stmt = delete(RbacRule)
        if owner_user_id is not None:
            stmt = stmt.where(RbacRule.owner_user_id == owner_user_id)
        if owner_tenant_id is not None:
            stmt = stmt.where(RbacRule.owner_tenant_id == owner_tenant_id)

        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def remove_rules_for_resource(
        self,
        *,
        resource_type: str,
        resource_id: UUID,
    ) -> int:
        stmt = delete(RbacRule).where(
            RbacRule.resource_type == resource_type,
            RbacRule.resource_id == resource_id,
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
