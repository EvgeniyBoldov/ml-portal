"""
PermissionService - RBAC for tool instances

Resolution logic:
- Priority: User > Tenant > Default
- Values: allowed, denied, undefined
- Default scope: only allowed/denied (no undefined), default is denied
- Tenant/User scope: can have undefined which inherits from parent
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.permission_set import PermissionSet, PermissionScope, PermissionValue
from app.repositories.permission_set_repository import PermissionSetRepository

logger = get_logger(__name__)


@dataclass
class EffectivePermissions:
    """Result of permission resolution for user/tenant context"""
    # instance_slug -> is_allowed
    instance_permissions: Dict[str, bool] = field(default_factory=dict)
    # agent_slug -> is_allowed
    agent_permissions: Dict[str, bool] = field(default_factory=dict)
    
    def is_instance_allowed(self, instance_slug: str) -> bool:
        """Check if instance is allowed. Default is denied."""
        return self.instance_permissions.get(instance_slug, False)
    
    def is_agent_allowed(self, agent_slug: str) -> bool:
        """Check if agent is allowed. Default is denied."""
        return self.agent_permissions.get(agent_slug, False)
    
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


class PermissionService:
    """
    RBAC service for tool instances.
    
    Hierarchy: Default → Tenant → User
    Resolution priority: User > Tenant > Default
    
    Values:
    - allowed: instance is accessible
    - denied: instance is not accessible
    - undefined: inherit from parent scope (only for tenant/user)
    
    Example:
        service = PermissionService(session)
        perms = await service.resolve_permissions(user_id, tenant_id)
        
        if perms.is_instance_allowed("jira-prod"):
            # Instance is accessible
            pass
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PermissionSetRepository(session)
    
    async def resolve_permissions(
        self,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> EffectivePermissions:
        """
        Resolve effective permissions for user/tenant context.
        
        Priority: User > Tenant > Default
        
        For each instance:
        1. Check User level - if allowed/denied, use it
        2. If undefined at User level, check Tenant level
        3. If undefined at Tenant level, check Default level
        4. If not specified anywhere - denied by default
        """
        perm_sets = await self.repo.get_all_for_context(user_id, tenant_id)
        
        default_perm: Optional[PermissionSet] = None
        tenant_perm: Optional[PermissionSet] = None
        user_perm: Optional[PermissionSet] = None
        
        for ps in perm_sets:
            if ps.scope == PermissionScope.DEFAULT.value:
                default_perm = ps
            elif ps.scope == PermissionScope.TENANT.value:
                tenant_perm = ps
            elif ps.scope == PermissionScope.USER.value:
                user_perm = ps
        
        # Collect all instance slugs from all scopes
        all_instances: Set[str] = set()
        for ps in [default_perm, tenant_perm, user_perm]:
            if ps and ps.instance_permissions:
                all_instances.update(ps.instance_permissions.keys())
        
        # Collect all agent slugs from all scopes
        all_agents: Set[str] = set()
        for ps in [default_perm, tenant_perm, user_perm]:
            if ps and ps.agent_permissions:
                all_agents.update(ps.agent_permissions.keys())
        
        effective = EffectivePermissions()
        
        # Resolve instance permissions
        for instance_slug in all_instances:
            allowed = self._resolve_permission(
                instance_slug, 'instance', default_perm, tenant_perm, user_perm
            )
            effective.instance_permissions[instance_slug] = allowed
        
        # Resolve agent permissions
        for agent_slug in all_agents:
            allowed = self._resolve_permission(
                agent_slug, 'agent', default_perm, tenant_perm, user_perm
            )
            effective.agent_permissions[agent_slug] = allowed
        
        logger.debug(
            f"Resolved permissions for user={user_id}, tenant={tenant_id}: "
            f"instances: allowed={len(effective.get_allowed_instances())}, denied={len(effective.get_denied_instances())}; "
            f"agents: allowed={len(effective.get_allowed_agents())}, denied={len(effective.get_denied_agents())}"
        )
        
        return effective
    
    def _resolve_permission(
        self,
        slug: str,
        perm_type: str,  # 'instance' or 'agent'
        default_perm: Optional[PermissionSet],
        tenant_perm: Optional[PermissionSet],
        user_perm: Optional[PermissionSet],
    ) -> bool:
        """
        Resolve permission for a single instance or agent.
        
        Priority: User > Tenant > Default
        Returns True if allowed, False if denied.
        """
        def get_perms(ps: Optional[PermissionSet]) -> Optional[Dict[str, str]]:
            if not ps:
                return None
            if perm_type == 'instance':
                return ps.instance_permissions
            elif perm_type == 'agent':
                return ps.agent_permissions
            return None
        
        # Check user level first
        user_perms = get_perms(user_perm)
        if user_perms:
            value = user_perms.get(slug)
            if value == PermissionValue.ALLOWED.value:
                return True
            elif value == PermissionValue.DENIED.value:
                return False
            # undefined -> fall through to tenant
        
        # Check tenant level
        tenant_perms = get_perms(tenant_perm)
        if tenant_perms:
            value = tenant_perms.get(slug)
            if value == PermissionValue.ALLOWED.value:
                return True
            elif value == PermissionValue.DENIED.value:
                return False
            # undefined -> fall through to default
        
        # Check default level
        default_perms = get_perms(default_perm)
        if default_perms:
            value = default_perms.get(slug)
            if value == PermissionValue.ALLOWED.value:
                return True
            # denied or not specified -> denied
        
        # Not specified anywhere -> denied by default
        return False
    
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
    
    async def set_instance_permission(
        self,
        instance_slug: str,
        value: str,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """
        Set permission for an instance.
        
        Args:
            instance_slug: Instance slug
            value: "allowed", "denied", or "undefined" (only for tenant/user)
            scope: "default", "tenant", or "user"
            tenant_id: Required for tenant/user scope
            user_id: Required for user scope
        """
        # Validate value
        if scope == PermissionScope.DEFAULT.value:
            if value not in [PermissionValue.ALLOWED.value, PermissionValue.DENIED.value]:
                raise ValueError("Default scope can only have 'allowed' or 'denied'")
        else:
            if value not in [PermissionValue.ALLOWED.value, PermissionValue.DENIED.value, PermissionValue.UNDEFINED.value]:
                raise ValueError("Invalid permission value")
        
        perm_set = await self._get_or_create_perm_set(scope, tenant_id, user_id)
        
        # Update instance_permissions
        perms = dict(perm_set.instance_permissions or {})
        
        if value == PermissionValue.UNDEFINED.value:
            # Remove from dict to inherit from parent
            perms.pop(instance_slug, None)
        else:
            perms[instance_slug] = value
        
        perm_set.instance_permissions = perms
        return await self.repo.update(perm_set)
    
    async def set_agent_permission(
        self,
        agent_slug: str,
        value: str,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """
        Set permission for an agent.
        
        Args:
            agent_slug: Agent slug
            value: "allowed", "denied", or "undefined" (only for tenant/user)
            scope: "default", "tenant", or "user"
            tenant_id: Required for tenant/user scope
            user_id: Required for user scope
        """
        # Validate value
        if scope == PermissionScope.DEFAULT.value:
            if value not in [PermissionValue.ALLOWED.value, PermissionValue.DENIED.value]:
                raise ValueError("Default scope can only have 'allowed' or 'denied'")
        else:
            if value not in [PermissionValue.ALLOWED.value, PermissionValue.DENIED.value, PermissionValue.UNDEFINED.value]:
                raise ValueError("Invalid permission value")
        
        perm_set = await self._get_or_create_perm_set(scope, tenant_id, user_id)
        
        # Update agent_permissions
        perms = dict(perm_set.agent_permissions or {})
        
        if value == PermissionValue.UNDEFINED.value:
            # Remove from dict to inherit from parent
            perms.pop(agent_slug, None)
        else:
            perms[agent_slug] = value
        
        perm_set.agent_permissions = perms
        return await self.repo.update(perm_set)
    
    async def bulk_set_instance_permissions(
        self,
        permissions: Dict[str, str],
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """
        Set multiple instance permissions at once.
        
        Args:
            permissions: Dict of {instance_slug: value}
            scope: "default", "tenant", or "user"
        """
        perm_set = await self._get_or_create_perm_set(scope, tenant_id, user_id)
        
        perms = dict(perm_set.instance_permissions or {})
        
        for instance_slug, value in permissions.items():
            # Validate
            if scope == PermissionScope.DEFAULT.value:
                if value not in [PermissionValue.ALLOWED.value, PermissionValue.DENIED.value]:
                    raise ValueError(f"Default scope can only have 'allowed' or 'denied' for {instance_slug}")
            
            if value == PermissionValue.UNDEFINED.value:
                perms.pop(instance_slug, None)
            else:
                perms[instance_slug] = value
        
        perm_set.instance_permissions = perms
        return await self.repo.update(perm_set)
    
    async def get_permission_set(
        self,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> Optional[PermissionSet]:
        """Get permission set for given scope"""
        if scope == PermissionScope.DEFAULT.value:
            return await self.repo.get_default()
        elif scope == PermissionScope.TENANT.value:
            if not tenant_id:
                raise ValueError("tenant_id required for tenant scope")
            return await self.repo.get_for_tenant(tenant_id)
        elif scope == PermissionScope.USER.value:
            if not user_id or not tenant_id:
                raise ValueError("user_id and tenant_id required for user scope")
            return await self.repo.get_for_user(user_id, tenant_id)
        else:
            raise ValueError(f"Invalid scope: {scope}")
    
    async def _get_or_create_perm_set(
        self,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """Get or create permission set for given scope"""
        if scope == PermissionScope.DEFAULT.value:
            return await self.repo.get_or_create_default()
        elif scope == PermissionScope.TENANT.value:
            if not tenant_id:
                raise ValueError("tenant_id required for tenant scope")
            return await self.repo.get_or_create_for_tenant(tenant_id)
        elif scope == PermissionScope.USER.value:
            if not user_id or not tenant_id:
                raise ValueError("user_id and tenant_id required for user scope")
            return await self.repo.get_or_create_for_user(user_id, tenant_id)
        else:
            raise ValueError(f"Invalid scope: {scope}")
