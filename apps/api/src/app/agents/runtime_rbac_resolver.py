from __future__ import annotations

from typing import Callable, Iterable, Optional, Tuple, TypeVar
from uuid import UUID

from app.core.config import get_settings
from app.services.permission_service import EffectivePermissions, PermissionService

TAgent = TypeVar("TAgent")


class RuntimeRbacResolver:
    """Runtime RBAC facade.

    Keeps RBAC behavior in one place:
    - computes fallback policy for undefined resources
    - optionally resolves DB-backed RBAC rules
    """

    def __init__(self, permission_service: PermissionService) -> None:
        self.permission_service = permission_service
        settings = get_settings()
        self.enforce_rules = bool(getattr(settings, "RUNTIME_RBAC_ENFORCE_RULES", False))
        self.allow_undefined = bool(getattr(settings, "RUNTIME_RBAC_ALLOW_UNDEFINED", False))

    async def resolve_effective_permissions(
        self,
        *,
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        default_tool_allow: bool,
        default_collection_allow: bool,
    ) -> EffectivePermissions:
        effective_default_tool_allow = bool(default_tool_allow)
        effective_default_collection_allow = bool(default_collection_allow)

        # Test mode: for any undefined resource fallback to allow.
        if self.allow_undefined:
            effective_default_tool_allow = True
            effective_default_collection_allow = True

        if not self.enforce_rules:
            return EffectivePermissions(
                default_tool_allow=effective_default_tool_allow,
                default_collection_allow=effective_default_collection_allow,
            )

        return await self.permission_service.resolve_permissions(
            user_id=user_id,
            tenant_id=tenant_id,
            default_tool_allow=effective_default_tool_allow,
            default_collection_allow=effective_default_collection_allow,
        )

    def is_tool_allowed(
        self,
        effective_permissions: Optional[EffectivePermissions],
        tool_slug: str,
    ) -> bool:
        if not tool_slug.strip():
            return False
        if effective_permissions is None:
            return True
        return bool(effective_permissions.is_tool_allowed(tool_slug))

    def is_collection_allowed(
        self,
        effective_permissions: Optional[EffectivePermissions],
        collection_slug: Optional[str],
    ) -> bool:
        if not collection_slug:
            return True
        if effective_permissions is None:
            return True
        return bool(effective_permissions.is_collection_allowed(collection_slug))

    def is_agent_allowed(
        self,
        effective_permissions: Optional[EffectivePermissions],
        agent_slug: str,
        *,
        default_allow: bool = True,
    ) -> bool:
        if not agent_slug.strip():
            return False
        if effective_permissions is None:
            return default_allow
        if agent_slug in effective_permissions.agent_permissions:
            return bool(effective_permissions.agent_permissions[agent_slug])
        return bool(self.allow_undefined or default_allow)

    def filter_agents_by_slug(
        self,
        agents: Iterable[TAgent],
        *,
        effective_permissions: Optional[EffectivePermissions],
        slug_getter: Callable[[TAgent], Optional[str]],
        default_allow: bool = True,
    ) -> Tuple[list[TAgent], list[str]]:
        allowed: list[TAgent] = []
        denied_slugs: list[str] = []
        for agent in agents:
            slug = str(slug_getter(agent) or "").strip()
            if not slug:
                continue
            if self.is_agent_allowed(
                effective_permissions=effective_permissions,
                agent_slug=slug,
                default_allow=default_allow,
            ):
                allowed.append(agent)
            else:
                denied_slugs.append(slug)
        return allowed, denied_slugs
