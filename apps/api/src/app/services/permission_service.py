"""
PermissionService — unified RBAC resolution.

Single data source: RbacRule (flat, UUID-based, owner-bound).
Resolution priority: user > tenant > platform.
Default for unresolved resources: deny.

Runtime consumers use EffectivePermissions dataclass — interface unchanged.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rbac import RbacRule
from app.repositories.rbac_repository import RbacRuleRepository

logger = get_logger(__name__)


@dataclass
class EffectivePermissions:
    """Result of permission resolution for user/tenant context.

    Tool-level RBAC is intentionally absent: runtime access to operations is
    derived from collection access (agent → allowed_collections → data_instance
    → mcp → discovered tools). See architectural note in docs.
    """
    # instance_slug -> is_allowed
    instance_permissions: Dict[str, bool] = field(default_factory=dict)
    # agent_slug -> is_allowed
    agent_permissions: Dict[str, bool] = field(default_factory=dict)
    # collection_slug -> is_allowed
    collection_permissions: Dict[str, bool] = field(default_factory=dict)
    # RBAC denied reasons: resource -> reason
    denied_reasons: Dict[str, str] = field(default_factory=dict)
    # default fallback behavior for unresolved collection permissions
    default_collection_allow: bool = False

    def is_instance_allowed(self, instance_slug: str) -> bool:
        """Check if instance is allowed. Default is denied."""
        return self.instance_permissions.get(instance_slug, False)

    def is_agent_allowed(self, agent_slug: str) -> bool:
        """Check if agent is allowed. Default is denied."""
        return self.agent_permissions.get(agent_slug, False)

    def is_collection_allowed(self, collection_slug: str) -> bool:
        """Check if collection is allowed."""
        return self.collection_permissions.get(collection_slug, self.default_collection_allow)

    @property
    def allowed_collections(self) -> List[str]:
        """Get list of explicitly allowed collection slugs"""
        return [slug for slug, allowed in self.collection_permissions.items() if allowed]
    
    def get_allowed_instances(self) -> List[str]:
        """Get list of allowed instance slugs"""
        return [slug for slug, allowed in self.instance_permissions.items() if allowed]
    
    def get_denied_instances(self) -> List[str]:
        """Get list of denied instance slugs"""
        return [slug for slug, allowed in self.instance_permissions.items() if not allowed]
    
    def get_allowed_agents(self) -> List[str]:
        """Get list of allowed agent slugs"""
        return [slug for slug, allowed in self.agent_permissions.items() if allowed]
    
    def get_denied_agents(self) -> List[str]:
        """Get list of denied agent slugs"""
        return [slug for slug, allowed in self.agent_permissions.items() if not allowed]
    
    def filter_instances(self, instance_slugs: List[str]) -> List[str]:
        """Filter list of instances to only allowed ones"""
        return [i for i in instance_slugs if self.is_instance_allowed(i)]
    
    def filter_agents(self, agent_slugs: List[str]) -> List[str]:
        """Filter list of agents to only allowed ones"""
        return [a for a in agent_slugs if self.is_agent_allowed(a)]


# ── Slug lookup helpers (batch) ──────────────────────────────────────────

_RESOURCE_SLUG_MODELS = {
    "agent": ("app.models.agent", "Agent"),
    "instance": ("app.models.tool_instance", "ToolInstance"),
    "collection": ("app.models.collection", "Collection"),
}


async def _batch_resolve_slugs(
    session: AsyncSession,
    resource_type: str,
    resource_ids: set[UUID],
) -> Dict[UUID, str]:
    """Resolve resource UUIDs → slugs in a single query."""
    if not resource_ids:
        return {}
    entry = _RESOURCE_SLUG_MODELS.get(resource_type)
    if not entry:
        return {}
    import importlib
    mod = importlib.import_module(entry[0])
    model = getattr(mod, entry[1])
    stmt = select(model.id, model.slug).where(model.id.in_(resource_ids))
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def _batch_resolve_resource_targets(
    session: AsyncSession,
    resource_type: str,
    resource_ids: set[UUID],
) -> Dict[UUID, Tuple[str, str]]:
    """Resolve RBAC resource ids to logical runtime targets.

    Runtime RBAC consumes collection permissions by collection slug, but the
    admin RBAC surface historically stored collection-like resources as
    ``resource_type='instance'`` bound to ``Collection.id``. Support both:
    - ``collection`` -> collection slug
    - legacy ``instance`` + Collection.id -> collection slug
    - true ``instance`` + ToolInstance.id -> instance slug
    """
    if not resource_ids:
        return {}

    if resource_type == "instance":
        collection_slugs = await _batch_resolve_slugs(session, "collection", resource_ids)
        unresolved = {rid for rid in resource_ids if rid not in collection_slugs}
        instance_slugs = await _batch_resolve_slugs(session, "instance", unresolved)
        resolved: Dict[UUID, Tuple[str, str]] = {
            rid: (slug, "collection") for rid, slug in collection_slugs.items()
        }
        resolved.update({
            rid: (slug, "instance") for rid, slug in instance_slugs.items()
        })
        return resolved

    slugs = await _batch_resolve_slugs(session, resource_type, resource_ids)
    return {rid: (slug, resource_type) for rid, slug in slugs.items()}


class PermissionService:
    """
    Unified RBAC resolution service.

    Data source: RbacRule (flat rules with user > tenant > platform priority).
    No more PermissionSet — all access control goes through RbacRule.

    Example:
        service = PermissionService(session)
        perms = await service.resolve_permissions(user_id, tenant_id)
        if perms.is_instance_allowed("jira-prod"):
            ...
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.rule_repo = RbacRuleRepository(session)

    async def resolve_permissions(
        self,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        *,
        default_collection_allow: bool = False,
    ) -> EffectivePermissions:
        """
        Resolve effective permissions from RbacRule.

        Priority: user > tenant > platform > default deny.

        Tool-level RBAC is not part of this contract.
        """
        effective = EffectivePermissions(
            default_collection_allow=default_collection_allow,
        )

        # Load all applicable rules in priority order
        platform_rules = await self.rule_repo.list_platform_rules()
        tenant_rules = (
            await self.rule_repo.list_by_tenant(tenant_id) if tenant_id else []
        )
        user_rules = (
            await self.rule_repo.list_by_user(user_id) if user_id else []
        )

        # Build resolved map: (resource_type, resource_id) → effect
        # Apply in order platform → tenant → user (higher priority overwrites)
        resolved: Dict[tuple, tuple] = {}  # (type, id) → (effect, level)

        for rule in platform_rules:
            key = (rule.resource_type, rule.resource_id)
            resolved[key] = (rule.effect, "platform")

        for rule in tenant_rules:
            key = (rule.resource_type, rule.resource_id)
            resolved[key] = (rule.effect, "tenant")

        for rule in user_rules:
            key = (rule.resource_type, rule.resource_id)
            resolved[key] = (rule.effect, "user")

        # Batch-resolve slugs per resource type
        ids_by_type: Dict[str, set] = {}
        for (rtype, rid) in resolved:
            ids_by_type.setdefault(rtype, set()).add(rid)

        slug_maps: Dict[str, Dict[UUID, Tuple[str, str]]] = {}
        for rtype, ids in ids_by_type.items():
            slug_maps[rtype] = await _batch_resolve_resource_targets(
                self.session, rtype, ids
            )

        # Apply resolved effects to EffectivePermissions
        for (rtype, rid), (effect, level) in resolved.items():
            resolved_target = slug_maps.get(rtype, {}).get(rid)
            if not resolved_target:
                continue
            slug, logical_resource_type = resolved_target

            is_allowed = effect == "allow"

            if logical_resource_type == "instance":
                effective.instance_permissions[slug] = is_allowed
            elif logical_resource_type == "agent":
                effective.agent_permissions[slug] = is_allowed
            elif logical_resource_type == "collection":
                effective.collection_permissions[slug] = is_allowed

            if not is_allowed:
                effective.denied_reasons[slug] = (
                    f"Denied by RBAC rule ({level} level)"
                )

        logger.debug(
            f"Resolved permissions for user={user_id}, tenant={tenant_id}: "
            f"instances: allowed={len(effective.get_allowed_instances())}, "
            f"denied={len(effective.get_denied_instances())}; "
            f"agents: allowed={len(effective.get_allowed_agents())}, "
            f"denied={len(effective.get_denied_agents())}; "
            f"collections: {len(effective.collection_permissions)} rules"
        )

        return effective

    async def check_instance_permission(
        self,
        instance_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Quick check if a single instance is allowed"""
        perms = await self.resolve_permissions(user_id, tenant_id)
        return perms.is_instance_allowed(instance_slug)

    async def check_agent_permission(
        self,
        agent_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Quick check if a single agent is allowed"""
        perms = await self.resolve_permissions(user_id, tenant_id)
        return perms.is_agent_allowed(agent_slug)
