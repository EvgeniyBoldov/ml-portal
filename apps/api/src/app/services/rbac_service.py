"""
RBAC Service v3 — flat business logic for RbacRule (no policy container).

Handles:
- CRUD for RbacRule (individual access rules with direct owner binding)
- check_access(user_id, tenant_id, resource_type, resource_id) → allow/deny
- Auto-creation of platform deny rules when resources are created
- Enriched rule listing with resource names
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import RbacRule, RbacLevel, ResourceType, RbacEffect
from app.repositories.rbac_repository import RbacRuleRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class RbacRuleNotFoundError(Exception):
    pass


class RbacRuleDuplicateError(Exception):
    pass


class RbacService:
    """Service for flat RBAC operations (v3)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.rule_repo = RbacRuleRepository(session)

    # ─── Rule CRUD ────────────────────────────────────────────────────

    async def get_rule(self, rule_id: UUID) -> RbacRule:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise RbacRuleNotFoundError(f"RBAC rule '{rule_id}' not found")
        return rule

    async def create_rule(
        self,
        level: str,
        resource_type: str,
        resource_id: UUID,
        effect: str,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: bool = False,
        created_by_user_id: Optional[UUID] = None,
    ) -> RbacRule:
        rule = RbacRule(
            level=level,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=effect,
            created_by_user_id=created_by_user_id,
        )
        result = await self.rule_repo.create(rule)
        owner = "platform" if owner_platform else (
            f"user:{owner_user_id}" if owner_user_id else f"tenant:{owner_tenant_id}"
        )
        logger.info(
            f"Created RBAC rule: {owner}:{resource_type}:{resource_id}={effect}"
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

    async def list_rules(
        self,
        *,
        level: Optional[str] = None,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: Optional[bool] = None,
        resource_type: Optional[str] = None,
        effect: Optional[str] = None,
        skip: int = 0,
        limit: int = 500,
    ) -> List[RbacRule]:
        return await self.rule_repo.list_all_rules(
            level=level,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
            resource_type=resource_type,
            effect=effect,
            skip=skip,
            limit=limit,
        )

    # ─── Access Check ─────────────────────────────────────────────────

    async def check_access(
        self,
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
            user_id, tenant_id, resource_type, resource_id
        )

    # ─── Auto-create platform deny ────────────────────────────────────

    async def ensure_platform_deny(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> Optional[RbacRule]:
        """
        Ensure a platform deny rule exists for a resource.
        Called automatically when a new resource (agent, tool, etc.) is created.
        """
        existing = await self.rule_repo._find_platform_rule(resource_type, resource_id)
        if existing:
            return None

        rule = RbacRule(
            level=RbacLevel.PLATFORM.value,
            owner_platform=True,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=RbacEffect.DENY.value,
        )
        result = await self.rule_repo.create(rule)
        logger.info(f"Auto-created platform deny for {resource_type}:{resource_id}")
        return result

    async def set_platform_effect(
        self,
        resource_type: str,
        resource_id: UUID,
        effect: str,
    ) -> RbacRule:
        """
        Set or update the platform-level effect for a resource.
        Used for global release (allow) or rollback (deny).
        """
        existing = await self.rule_repo._find_platform_rule(resource_type, resource_id)
        if existing:
            existing.effect = effect
            return await self.rule_repo.update(existing)

        rule = RbacRule(
            level=RbacLevel.PLATFORM.value,
            owner_platform=True,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=effect,
        )
        return await self.rule_repo.create(rule)

    # ─── Enriched listing ─────────────────────────────────────────────

    async def list_enriched_rules(
        self,
        *,
        level: Optional[str] = None,
        owner_user_id: Optional[UUID] = None,
        owner_tenant_id: Optional[UUID] = None,
        owner_platform: Optional[bool] = None,
        resource_type: Optional[str] = None,
        effect: Optional[str] = None,
        skip: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        List rules with enriched data: owner info + resource names.
        """
        from sqlalchemy import select
        from app.models.agent import Agent
        from app.models.tool_group import ToolGroup
        from app.models.tool_instance import ToolInstance
        from app.models.tool import Tool
        from app.models.user import Users
        from app.models.tenant import Tenants

        rules = await self.rule_repo.list_all_rules(
            level=level,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
            resource_type=resource_type,
            effect=effect,
            skip=skip,
            limit=limit,
        )

        if not rules:
            return []

        # Collect resource IDs by type for batch loading
        resource_ids: Dict[str, set] = {
            "agent": set(), "toolgroup": set(), "tool": set(), "instance": set(),
        }
        owner_user_ids: set = set()
        owner_tenant_ids: set = set()

        for rule in rules:
            if rule.resource_type in resource_ids:
                resource_ids[rule.resource_type].add(rule.resource_id)
            if rule.owner_user_id:
                owner_user_ids.add(rule.owner_user_id)
            if rule.owner_tenant_id:
                owner_tenant_ids.add(rule.owner_tenant_id)

        # Batch load resource names
        name_map: Dict[str, Dict[UUID, str]] = {
            "agent": {}, "toolgroup": {}, "tool": {}, "instance": {},
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

        # Batch load owner names
        owner_map: Dict[UUID, str] = {}

        if owner_tenant_ids:
            stmt = select(Tenants.id, Tenants.name).where(Tenants.id.in_(owner_tenant_ids))
            result = await self.session.execute(stmt)
            owner_map.update({row[0]: row[1] for row in result.all()})

        if owner_user_ids:
            stmt = select(Users.id, Users.login).where(Users.id.in_(owner_user_ids))
            result = await self.session.execute(stmt)
            owner_map.update({row[0]: row[1] for row in result.all()})

        # Build enriched response
        enriched = []
        for rule in rules:
            resource_name = name_map.get(rule.resource_type, {}).get(
                rule.resource_id, str(rule.resource_id)[:8] + "..."
            )
            
            if rule.owner_platform:
                owner_name = "Platform"
            elif rule.owner_user_id:
                owner_name = owner_map.get(rule.owner_user_id, str(rule.owner_user_id)[:8])
            elif rule.owner_tenant_id:
                owner_name = owner_map.get(rule.owner_tenant_id, str(rule.owner_tenant_id)[:8])
            else:
                owner_name = "Unknown"

            enriched.append({
                "id": str(rule.id),
                "owner": {
                    "level": rule.level,
                    "name": owner_name,
                    "user_id": str(rule.owner_user_id) if rule.owner_user_id else None,
                    "tenant_id": str(rule.owner_tenant_id) if rule.owner_tenant_id else None,
                    "platform": rule.owner_platform,
                },
                "resource": {
                    "type": rule.resource_type,
                    "id": str(rule.resource_id),
                    "name": resource_name,
                },
                "effect": rule.effect,
                "created_at": rule.created_at.isoformat(),
                "created_by_user_id": str(rule.created_by_user_id) if rule.created_by_user_id else None,
            })

        return enriched
