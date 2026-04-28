from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.agents.contracts import OperationCredentialContext, ResolvedOperation
from app.agents.credential_resolver import RuntimeCredentialResolver
from app.agents.operation_builder import OperationBuilder
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.collection_tool_resolver import CollectionToolResolver
from app.services.permission_service import EffectivePermissions


class RuntimeOperationResolver:
    """Resolve runtime operations for instance/provider pair via dedicated builder."""

    def __init__(
        self,
        *,
        operation_builder: OperationBuilder,
        collection_tool_resolver: CollectionToolResolver,
        credential_resolver: RuntimeCredentialResolver,
    ) -> None:
        self.operation_builder = operation_builder
        self.collection_tool_resolver = collection_tool_resolver
        self.credential_resolver = credential_resolver

    async def resolve_for_instance(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
        runtime_domain: Optional[str] = None,
        has_credentials: Optional[bool] = None,
        effective_permissions: Optional[EffectivePermissions] = None,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> List[tuple[ResolvedOperation, Optional[OperationCredentialContext]]]:
        resolved_runtime_domain = str(
            runtime_domain if runtime_domain is not None else (instance.domain or "")
        ).strip()
        context_domains = (
            [resolved_runtime_domain]
            if resolved_runtime_domain.startswith("collection.")
            else None
        )
        return await self.operation_builder.build_operations_for_instance(
            instance=instance,
            provider=provider,
            runtime_domain=resolved_runtime_domain,
            context_domains=context_domains,
            has_credentials=has_credentials,
            effective_permissions=effective_permissions,
            user_id=user_id,
            tenant_id=tenant_id,
            load_discovered_capabilities=self._load_discovered_capabilities,
            resolve_execution_credentials=self._resolve_execution_credentials,
        )

    async def _resolve_execution_credentials(
        self,
        instance: ToolInstance,
        *,
        user_id: UUID,
        tenant_id: UUID,
        tool_slug: Optional[str] = None,
        operation: Optional[str] = None,
        credential_scope: str = "auto",
        risk_level: str = "safe",
        side_effects: bool = False,
        requires_confirmation: bool = False,
    ) -> Optional[OperationCredentialContext]:
        return await self.credential_resolver.resolve_for_execution(
            instance,
            user_id=user_id,
            tenant_id=tenant_id,
            tool_slug=tool_slug,
            operation=operation,
            credential_scope=credential_scope,
            risk_level=risk_level,
            side_effects=side_effects,
            requires_confirmation=requires_confirmation,
        )

    async def _load_discovered_capabilities(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
    ) -> List[DiscoveredTool]:
        return await self.collection_tool_resolver.load_discovered_tools(
            instance=instance,
            provider=provider,
        )
