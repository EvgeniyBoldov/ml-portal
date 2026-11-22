"""
RBAC Repository v3 — flat data access for RbacRule (no policy container).

Rules are bound directly to owners (user/tenant/platform).
"""
from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import RbacEffect, RbacLevel, RbacRule
from app.core.logging import get_logger

logger = get_logger(__name__)


class RbacRuleRepository:
    """Repository for flat RbacRule CRUD and access checks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, rule: RbacRule) -> RbacRule:
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule


    async def get_by_id(self, rule_id: UUID) -> Optional[RbacRule]:
        return await self.session.get(RbacRule, rule_id)

    # ─── Owner-based queries ─────────────────────────────────────────

    async def list_by_user(
        self,
        user_id: UUID,
        resource_type: Optional[str] = None,
    ) -> List[RbacRule]:
        """List all rules owned by a specific user."""
        stmt = select(RbacRule).where(RbacRule.owner_user_id == user_id)
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        stmt = stmt.order_by(RbacRule.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        resource_type: Optional[str] = None,
    ) -> List[RbacRule]:
        """List all rules owned by a specific tenant."""
        stmt = select(RbacRule).where(RbacRule.owner_tenant_id == tenant_id)
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        stmt = stmt.order_by(RbacRule.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_platform_rules(
        self,
        resource_type: Optional[str] = None,
    ) -> List[RbacRule]:
        """List all platform-level rules."""
        stmt = select(RbacRule).where(RbacRule.owner_platform == True)  # noqa: E712
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        stmt = stmt.order_by(RbacRule.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ─── Access check (user > tenant > platform) ─────────────────────

    async def _find_user_rule(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        stmt = select(RbacRule).where(and_(
            RbacRule.owner_user_id == user_id,
            RbacRule.resource_type == resource_type,
            RbacRule.resource_id == resource_id,
        ))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_tenant_rule(
        self,
        tenant_id: UUID,
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        stmt = select(RbacRule).where(and_(
            RbacRule.owner_tenant_id == tenant_id,
            RbacRule.resource_type == resource_type,
            RbacRule.resource_id == resource_id,
        ))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_platform_rule(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        stmt = select(RbacRule).where(and_(
            RbacRule.owner_platform == True,  # noqa: E712
            RbacRule.resource_type == resource_type,
            RbacRule.resource_id == resource_id,
        ))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def iter_access_rules(
        self,
        user_id: UUID | None,
        tenant_id: UUID | None,
        resource_type: str,
        resource_id: UUID,
    ) -> AsyncIterator[tuple[RbacLevel, RbacRule | None]]:
        """Look up applicable scopes in descending priority."""
        if user_id is not None:
            yield RbacLevel.USER, await self._find_user_rule(user_id, resource_type, resource_id)
        if tenant_id is not None:
            yield RbacLevel.TENANT, await self._find_tenant_rule(tenant_id, resource_type, resource_id)
        yield RbacLevel.PLATFORM, await self._find_platform_rule(resource_type, resource_id)

    async def check_access(
        self,
        user_id: UUID,
        tenant_id: UUID,
        resource_type: str,
        resource_id: UUID,
    ) -> str:
        """Return the first applicable rule's effect, or deny by default."""
        async for _, rule in self.iter_access_rules(user_id, tenant_id, resource_type, resource_id):
            if rule is not None:
                return rule.effect
        return RbacEffect.DENY.value

    async def update(self, rule: RbacRule) -> RbacRule:
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def delete(self, rule: RbacRule) -> None:
        await self.session.delete(rule)
        await self.session.flush()

    async def list_all_rules(
        self,
        *,
        level: Optional[str] = None,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: Optional[bool] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        effect: Optional[str] = None,
        skip: int = 0,
        limit: int = 500,
    ) -> List[RbacRule]:
        """List rules with optional filters."""
        stmt = select(RbacRule)

        if level:
            stmt = stmt.where(RbacRule.level == level)
        if owner_user_id is not None:
            stmt = stmt.where(RbacRule.owner_user_id == owner_user_id)
        if owner_tenant_id is not None:
            stmt = stmt.where(RbacRule.owner_tenant_id == owner_tenant_id)
        if owner_platform is not None:
            stmt = stmt.where(RbacRule.owner_platform == owner_platform)
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(RbacRule.resource_id == resource_id)
        if effect:
            stmt = stmt.where(RbacRule.effect == effect)

        stmt = stmt.order_by(
            RbacRule.resource_type,
            RbacRule.created_at,
            RbacRule.id,
        ).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

