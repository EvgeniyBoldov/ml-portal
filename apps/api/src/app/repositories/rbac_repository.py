"""
RBAC Repository — data access for RbacPolicy and RbacRule.
"""
from __future__ import annotations
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rbac import RbacPolicy, RbacRule
from app.core.logging import get_logger

logger = get_logger(__name__)


class RbacPolicyRepository:
    """Repository for RbacPolicy CRUD."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, policy: RbacPolicy) -> RbacPolicy:
        self.session.add(policy)
        await self.session.flush()
        await self.session.refresh(policy, attribute_names=["rules"])
        return policy

    async def get_by_id(self, policy_id: UUID) -> Optional[RbacPolicy]:
        stmt = (
            select(RbacPolicy)
            .options(selectinload(RbacPolicy.rules))
            .where(RbacPolicy.id == policy_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[RbacPolicy]:
        stmt = (
            select(RbacPolicy)
            .options(selectinload(RbacPolicy.rules))
            .where(RbacPolicy.slug == slug)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[RbacPolicy]:
        stmt = (
            select(RbacPolicy)
            .options(selectinload(RbacPolicy.rules))
            .order_by(RbacPolicy.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, policy: RbacPolicy) -> RbacPolicy:
        await self.session.flush()
        await self.session.refresh(policy)
        return policy

    async def delete(self, policy: RbacPolicy) -> None:
        await self.session.delete(policy)
        await self.session.flush()


class RbacRuleRepository:
    """Repository for RbacRule CRUD and access checks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, rule: RbacRule) -> RbacRule:
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def bulk_create(self, rules: List[RbacRule]) -> List[RbacRule]:
        self.session.add_all(rules)
        await self.session.flush()
        for rule in rules:
            await self.session.refresh(rule)
        return rules

    async def get_by_id(self, rule_id: UUID) -> Optional[RbacRule]:
        return await self.session.get(RbacRule, rule_id)

    async def list_by_policy(
        self,
        rbac_policy_id: UUID,
        level: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[RbacRule]:
        stmt = select(RbacRule).where(RbacRule.rbac_policy_id == rbac_policy_id)
        if level:
            stmt = stmt.where(RbacRule.level == level)
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        stmt = stmt.order_by(RbacRule.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_rule(
        self,
        rbac_policy_id: UUID,
        level: str,
        level_id: Optional[UUID],
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        """Find a specific rule by all key fields."""
        conditions = [
            RbacRule.rbac_policy_id == rbac_policy_id,
            RbacRule.level == level,
            RbacRule.resource_type == resource_type,
            RbacRule.resource_id == resource_id,
        ]
        if level_id is None:
            conditions.append(RbacRule.level_id.is_(None))
        else:
            conditions.append(RbacRule.level_id == level_id)

        stmt = select(RbacRule).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def check_access(
        self,
        rbac_policy_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        resource_type: str,
        resource_id: UUID,
    ) -> str:
        """
        Deterministic access check: user → tenant → platform → deny.

        Returns 'allow' or 'deny'.
        """
        # 1. User level
        rule = await self.find_rule(
            rbac_policy_id, "user", user_id, resource_type, resource_id
        )
        if rule:
            return rule.effect

        # 2. Tenant level
        rule = await self.find_rule(
            rbac_policy_id, "tenant", tenant_id, resource_type, resource_id
        )
        if rule:
            return rule.effect

        # 3. Platform level
        rule = await self.find_rule(
            rbac_policy_id, "platform", None, resource_type, resource_id
        )
        if rule:
            return rule.effect

        # 4. Default deny
        return "deny"

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
        rbac_policy_id: Optional[UUID] = None,
        level: Optional[str] = None,
        level_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        effect: Optional[str] = None,
        skip: int = 0,
        limit: int = 500,
    ) -> List[RbacRule]:
        """
        List rules across all policies with optional filters.
        Returns rules with rbac_policy relationship loaded.
        """
        stmt = (
            select(RbacRule)
            .options(selectinload(RbacRule.rbac_policy))
        )

        if rbac_policy_id:
            stmt = stmt.where(RbacRule.rbac_policy_id == rbac_policy_id)
        if level:
            stmt = stmt.where(RbacRule.level == level)
        if level_id is not None:
            stmt = stmt.where(RbacRule.level_id == level_id)
        if resource_type:
            stmt = stmt.where(RbacRule.resource_type == resource_type)
        if effect:
            stmt = stmt.where(RbacRule.effect == effect)

        stmt = stmt.order_by(
            RbacRule.rbac_policy_id,
            RbacRule.resource_type,
            RbacRule.created_at,
        ).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_policy(self, rbac_policy_id: UUID) -> int:
        """Delete all rules for a policy. Returns count of deleted rows."""
        stmt = delete(RbacRule).where(RbacRule.rbac_policy_id == rbac_policy_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
