from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.core.config import get_settings
from app.services.permission_service import EffectivePermissions, PermissionService


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
