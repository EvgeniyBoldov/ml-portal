"""
RBAC Service — business logic for RBAC policies and rules.

Handles:
- CRUD for RbacPolicy (named sets of rules)
- CRUD for RbacRule (individual access rules)
- check_access(user_id, tenant_id, resource_type, resource_id) → allow/deny
- Auto-creation of platform deny rules when resources are created
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import RbacPolicy, RbacRule, RbacLevel, ResourceType, RbacEffect
from app.repositories.rbac_repository import RbacPolicyRepository, RbacRuleRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class RbacPolicyNotFoundError(Exception):
    pass


class RbacRuleNotFoundError(Exception):
    pass


class RbacRuleDuplicateError(Exception):
    pass


class RbacService:
    """Service for RBAC operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.policy_repo = RbacPolicyRepository(session)
        self.rule_repo = RbacRuleRepository(session)

    # ─── Policy CRUD ──────────────────────────────────────────────────

    async def list_policies(self, skip: int = 0, limit: int = 100) -> List[RbacPolicy]:
        return await self.policy_repo.list_all(skip=skip, limit=limit)

    async def get_policy_by_slug(self, slug: str) -> RbacPolicy:
        policy = await self.policy_repo.get_by_slug(slug)
        if not policy:
            raise RbacPolicyNotFoundError(f"RBAC policy '{slug}' not found")
        return policy

    async def get_policy_by_id(self, policy_id: UUID) -> RbacPolicy:
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            raise RbacPolicyNotFoundError(f"RBAC policy '{policy_id}' not found")
        return policy

    async def create_policy(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
    ) -> RbacPolicy:
        policy = RbacPolicy(
            slug=slug,
            name=name,
            description=description,
        )
        return await self.policy_repo.create(policy)

    async def update_policy(
        self,
        slug: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> RbacPolicy:
        policy = await self.get_policy_by_slug(slug)
        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        return await self.policy_repo.update(policy)

    async def delete_policy(self, slug: str) -> None:
        policy = await self.get_policy_by_slug(slug)
        await self.policy_repo.delete(policy)

    # ─── Rule CRUD ────────────────────────────────────────────────────

    async def list_rules(
        self,
        policy_slug: str,
        level: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[RbacRule]:
        policy = await self.get_policy_by_slug(policy_slug)
        return await self.rule_repo.list_by_policy(
            policy.id, level=level, resource_type=resource_type
        )

    async def get_rule(self, rule_id: UUID) -> RbacRule:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise RbacRuleNotFoundError(f"RBAC rule '{rule_id}' not found")
        return rule

    async def create_rule(
        self,
        policy_slug: str,
        level: str,
        level_id: Optional[UUID],
        resource_type: str,
        resource_id: UUID,
        effect: str,
        created_by_user_id: Optional[UUID] = None,
    ) -> RbacRule:
        policy = await self.get_policy_by_slug(policy_slug)

        # Check for duplicate
        existing = await self.rule_repo.find_rule(
            policy.id, level, level_id, resource_type, resource_id
        )
        if existing:
            raise RbacRuleDuplicateError(
                f"Rule already exists for {level}:{resource_type}:{resource_id} "
                f"in policy '{policy_slug}'"
            )

        rule = RbacRule(
            rbac_policy_id=policy.id,
            level=level,
            level_id=level_id,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=effect,
            created_by_user_id=created_by_user_id,
        )
        result = await self.rule_repo.create(rule)
        logger.info(
            f"Created RBAC rule: {level}:{resource_type}:{resource_id}={effect} "
            f"in policy '{policy_slug}'"
        )
        return result

    async def update_rule(
        self,
        rule_id: UUID,
        effect: str,
    ) -> RbacRule:
        """Update rule effect (allow ↔ deny)."""
        rule = await self.get_rule(rule_id)
        rule.effect = effect
        result = await self.rule_repo.update(rule)
        logger.info(f"Updated RBAC rule {rule_id}: effect={effect}")
        return result

    async def delete_rule(self, rule_id: UUID) -> None:
        rule = await self.get_rule(rule_id)
        await self.rule_repo.delete(rule)
        logger.info(f"Deleted RBAC rule {rule_id}")

    # ─── Access Check ─────────────────────────────────────────────────

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
        return await self.rule_repo.check_access(
            rbac_policy_id, user_id, tenant_id, resource_type, resource_id
        )

    # ─── Auto-create platform deny ────────────────────────────────────

    async def ensure_platform_deny(
        self,
        rbac_policy_id: UUID,
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        """
        Ensure a platform deny rule exists for a resource.
        Called automatically when a new resource (agent, tool, etc.) is created.
        
        Returns the rule if created, None if already exists.
        """
        existing = await self.rule_repo.find_rule(
            rbac_policy_id, "platform", None, resource_type, resource_id
        )
        if existing:
            return None

        rule = RbacRule(
            rbac_policy_id=rbac_policy_id,
            level=RbacLevel.PLATFORM.value,
            level_id=None,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=RbacEffect.DENY.value,
        )
        result = await self.rule_repo.create(rule)
        logger.info(
            f"Auto-created platform deny for {resource_type}:{resource_id}"
        )
        return result

    async def list_enriched_rules(
        self,
        *,
        rbac_policy_id: Optional[UUID] = None,
        level: Optional[str] = None,
        level_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        effect: Optional[str] = None,
        skip: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        List rules with enriched data: policy info + resource names.
        Returns flat list for frontend to group as needed.
        """
        from sqlalchemy import select
        from app.models.agent import Agent
        from app.models.tool_group import ToolGroup
        from app.models.tool_instance import ToolInstance
        from app.models.tool import Tool
        from app.models.user import Users
        from app.models.tenant import Tenants

        rules = await self.rule_repo.list_all_rules(
            rbac_policy_id=rbac_policy_id,
            level=level,
            level_id=level_id,
            resource_type=resource_type,
            effect=effect,
            skip=skip,
            limit=limit,
        )

        if not rules:
            return []

        # Collect resource IDs by type for batch loading
        resource_ids: Dict[str, set] = {
            "agent": set(),
            "toolgroup": set(),
            "tool": set(),
            "instance": set(),
        }
        level_ids: Dict[str, set] = {"tenant": set(), "user": set()}

        for rule in rules:
            if rule.resource_type in resource_ids:
                resource_ids[rule.resource_type].add(rule.resource_id)
            if rule.level_id:
                if rule.level == "tenant":
                    level_ids["tenant"].add(rule.level_id)
                elif rule.level == "user":
                    level_ids["user"].add(rule.level_id)

        # Batch load resource names
        name_map: Dict[str, Dict[UUID, str]] = {
            "agent": {},
            "toolgroup": {},
            "tool": {},
            "instance": {},
        }

        if resource_ids["agent"]:
            stmt = select(Agent.id, Agent.name).where(Agent.id.in_(resource_ids["agent"]))
            result = await self.session.execute(stmt)
            name_map["agent"] = {row[0]: row[1] for row in result.all()}

        if resource_ids["toolgroup"]:
            stmt = select(ToolGroup.id, ToolGroup.name).where(ToolGroup.id.in_(resource_ids["toolgroup"]))
            result = await self.session.execute(stmt)
            name_map["toolgroup"] = {row[0]: row[1] for row in result.all()}

        if resource_ids["tool"]:
            stmt = select(Tool.id, Tool.name).where(Tool.id.in_(resource_ids["tool"]))
            result = await self.session.execute(stmt)
            name_map["tool"] = {row[0]: row[1] for row in result.all()}

        if resource_ids["instance"]:
            stmt = select(ToolInstance.id, ToolInstance.name).where(ToolInstance.id.in_(resource_ids["instance"]))
            result = await self.session.execute(stmt)
            name_map["instance"] = {row[0]: row[1] for row in result.all()}

        # Batch load level context names
        context_map: Dict[UUID, str] = {}

        if level_ids["tenant"]:
            stmt = select(Tenants.id, Tenants.name).where(Tenants.id.in_(level_ids["tenant"]))
            result = await self.session.execute(stmt)
            context_map.update({row[0]: row[1] for row in result.all()})

        if level_ids["user"]:
            stmt = select(Users.id, Users.login).where(Users.id.in_(level_ids["user"]))
            result = await self.session.execute(stmt)
            context_map.update({row[0]: row[1] for row in result.all()})

        # Build enriched response
        enriched = []
        for rule in rules:
            resource_name = name_map.get(rule.resource_type, {}).get(
                rule.resource_id, str(rule.resource_id)[:8] + "..."
            )
            context_name = context_map.get(rule.level_id) if rule.level_id else None

            enriched.append({
                "id": str(rule.id),
                "policy": {
                    "id": str(rule.rbac_policy.id),
                    "slug": rule.rbac_policy.slug,
                    "name": rule.rbac_policy.name,
                },
                "resource": {
                    "type": rule.resource_type,
                    "id": str(rule.resource_id),
                    "name": resource_name,
                },
                "rule": {
                    "effect": rule.effect,
                    "level": rule.level,
                    "level_id": str(rule.level_id) if rule.level_id else None,
                    "context_name": context_name,
                    "created_at": rule.created_at.isoformat(),
                    "created_by_user_id": str(rule.created_by_user_id) if rule.created_by_user_id else None,
                },
            })

        return enriched

    async def set_platform_effect(
        self,
        rbac_policy_id: UUID,
        resource_type: str,
        resource_id: UUID,
        effect: str,
    ) -> RbacRule:
        """
        Set or update the platform-level effect for a resource.
        Used for global release (allow) or rollback (deny).
        """
        existing = await self.rule_repo.find_rule(
            rbac_policy_id, "platform", None, resource_type, resource_id
        )
        if existing:
            existing.effect = effect
            return await self.rule_repo.update(existing)

        rule = RbacRule(
            rbac_policy_id=rbac_policy_id,
            level=RbacLevel.PLATFORM.value,
            level_id=None,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=effect,
        )
        return await self.rule_repo.create(rule)
