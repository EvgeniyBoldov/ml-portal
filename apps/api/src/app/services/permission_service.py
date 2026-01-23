"""
PermissionService - резолв прав доступа к tools и collections

Логика резолва:
- Приоритет: User > Tenant > Default
- Если на уровне User есть явное разрешение/запрет - используем его
- Иначе проверяем Tenant, затем Default
- Если нигде не указано - запрещено по умолчанию
"""
from dataclasses import dataclass, field
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.permission_set import PermissionSet, PermissionScope
from app.repositories.permission_set_repository import PermissionSetRepository

logger = get_logger(__name__)


@dataclass
class EffectivePermissions:
    """Результат резолва прав для контекста user/tenant"""
    allowed_tools: Set[str] = field(default_factory=set)
    denied_tools: Set[str] = field(default_factory=set)
    allowed_collections: Set[str] = field(default_factory=set)
    denied_collections: Set[str] = field(default_factory=set)
    
    def is_tool_allowed(self, tool_slug: str) -> bool:
        """Check if tool is allowed"""
        if tool_slug in self.denied_tools:
            return False
        return tool_slug in self.allowed_tools
    
    def is_collection_allowed(self, collection_slug: str) -> bool:
        """Check if collection is allowed"""
        if collection_slug in self.denied_collections:
            return False
        return collection_slug in self.allowed_collections
    
    def filter_tools(self, tool_slugs: List[str]) -> List[str]:
        """Filter list of tools to only allowed ones"""
        return [t for t in tool_slugs if self.is_tool_allowed(t)]
    
    def filter_collections(self, collection_slugs: List[str]) -> List[str]:
        """Filter list of collections to only allowed ones"""
        return [c for c in collection_slugs if self.is_collection_allowed(c)]


class PermissionService:
    """
    Сервис для работы с правами доступа.
    
    Иерархия наследования: Default → Tenant → User
    Приоритет при резолве: User > Tenant > Default
    
    Пример:
        service = PermissionService(session)
        perms = await service.resolve_permissions(user_id, tenant_id)
        
        if perms.is_tool_allowed("jira.create"):
            # Tool доступен
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
        
        For each tool/collection:
        1. Check User level - if explicitly allowed/denied, use it
        2. If not specified at User level, check Tenant level
        3. If not specified at Tenant level, check Default level
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
        
        effective = EffectivePermissions()
        
        all_tools = self._collect_all_items(
            default_perm, tenant_perm, user_perm, "tools"
        )
        for tool_slug in all_tools:
            allowed = self._resolve_item_permission(
                tool_slug, default_perm, tenant_perm, user_perm, "tools"
            )
            if allowed:
                effective.allowed_tools.add(tool_slug)
            else:
                effective.denied_tools.add(tool_slug)
        
        all_collections = self._collect_all_items(
            default_perm, tenant_perm, user_perm, "collections"
        )
        for coll_slug in all_collections:
            allowed = self._resolve_item_permission(
                coll_slug, default_perm, tenant_perm, user_perm, "collections"
            )
            if allowed:
                effective.allowed_collections.add(coll_slug)
            else:
                effective.denied_collections.add(coll_slug)
        
        logger.debug(
            f"Resolved permissions for user={user_id}, tenant={tenant_id}: "
            f"tools={len(effective.allowed_tools)}, collections={len(effective.allowed_collections)}"
        )
        
        return effective
    
    def _collect_all_items(
        self,
        default_perm: Optional[PermissionSet],
        tenant_perm: Optional[PermissionSet],
        user_perm: Optional[PermissionSet],
        item_type: str,
    ) -> Set[str]:
        """Collect all unique items from all permission sets"""
        items = set()
        
        for ps in [default_perm, tenant_perm, user_perm]:
            if ps:
                allowed = getattr(ps, f"allowed_{item_type}", []) or []
                denied = getattr(ps, f"denied_{item_type}", []) or []
                items.update(allowed)
                items.update(denied)
        
        return items
    
    def _resolve_item_permission(
        self,
        item_slug: str,
        default_perm: Optional[PermissionSet],
        tenant_perm: Optional[PermissionSet],
        user_perm: Optional[PermissionSet],
        item_type: str,
    ) -> bool:
        """
        Resolve permission for a single item.
        
        Priority: User > Tenant > Default
        Returns True if allowed, False if denied.
        """
        for ps in [user_perm, tenant_perm, default_perm]:
            if ps is None:
                continue
            
            denied = getattr(ps, f"denied_{item_type}", []) or []
            if item_slug in denied:
                return False
            
            allowed = getattr(ps, f"allowed_{item_type}", []) or []
            if item_slug in allowed:
                return True
        
        return False
    
    async def check_tool_permission(
        self,
        tool_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Quick check if a single tool is allowed"""
        perms = await self.resolve_permissions(user_id, tenant_id)
        return perms.is_tool_allowed(tool_slug)
    
    async def check_collection_permission(
        self,
        collection_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> bool:
        """Quick check if a single collection is allowed"""
        perms = await self.resolve_permissions(user_id, tenant_id)
        return perms.is_collection_allowed(collection_slug)
    
    async def add_tool_permission(
        self,
        tool_slug: str,
        scope: str,
        allow: bool = True,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """Add or update tool permission"""
        perm_set = await self._get_or_create_perm_set(scope, tenant_id, user_id)
        
        if allow:
            if tool_slug not in perm_set.allowed_tools:
                perm_set.allowed_tools = list(perm_set.allowed_tools) + [tool_slug]
            if tool_slug in perm_set.denied_tools:
                perm_set.denied_tools = [t for t in perm_set.denied_tools if t != tool_slug]
        else:
            if tool_slug not in perm_set.denied_tools:
                perm_set.denied_tools = list(perm_set.denied_tools) + [tool_slug]
            if tool_slug in perm_set.allowed_tools:
                perm_set.allowed_tools = [t for t in perm_set.allowed_tools if t != tool_slug]
        
        return await self.repo.update(perm_set)
    
    async def add_collection_permission(
        self,
        collection_slug: str,
        scope: str,
        allow: bool = True,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> PermissionSet:
        """Add or update collection permission"""
        perm_set = await self._get_or_create_perm_set(scope, tenant_id, user_id)
        
        if allow:
            if collection_slug not in perm_set.allowed_collections:
                perm_set.allowed_collections = list(perm_set.allowed_collections) + [collection_slug]
            if collection_slug in perm_set.denied_collections:
                perm_set.denied_collections = [c for c in perm_set.denied_collections if c != collection_slug]
        else:
            if collection_slug not in perm_set.denied_collections:
                perm_set.denied_collections = list(perm_set.denied_collections) + [collection_slug]
            if collection_slug in perm_set.allowed_collections:
                perm_set.allowed_collections = [c for c in perm_set.allowed_collections if c != collection_slug]
        
        return await self.repo.update(perm_set)
    
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
