from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import (
    MissingRequirements,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.data_instance_resolver import RuntimeDataInstanceResolver
from app.agents.credential_resolver import RuntimeCredentialResolver
from app.agents.operation_resolver import RuntimeOperationResolver
from app.agents.operation_builder import OperationBuilder
from app.agents.runtime_graph import RuntimeExecutionGraph
from app.agents.runtime_graph_builder import RuntimeExecutionGraphBuilder
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.tool_resolver import ToolResolver
from app.core.logging import get_logger
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.services.credential_service import CredentialService
from app.services.permission_service import EffectivePermissions, PermissionService
from app.services.tool_instance_service import ToolInstanceService
from app.services.collection_binding import (
    has_collection_binding,
    extract_collection_binding,
)
from app.services.collection_tool_resolver import CollectionToolResolver
from app.core.config import get_settings

logger = get_logger(__name__)

@dataclass
class OperationResolveResult:
    effective_permissions: EffectivePermissions
    resolved_data_instances: List[ResolvedDataInstance] = field(default_factory=list)
    resolved_operations: List[ResolvedOperation] = field(default_factory=list)
    execution_graph: RuntimeExecutionGraph = field(default_factory=RuntimeExecutionGraph)
    missing: MissingRequirements = field(default_factory=MissingRequirements)


class OperationRouter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.credential_service = CredentialService(session)
        self.permission_service = PermissionService(session)
        self.runtime_rbac_resolver = RuntimeRbacResolver(self.permission_service)
        self.instance_service = ToolInstanceService(session)
        self.tool_resolver = ToolResolver(session)
        self.operation_builder = OperationBuilder(
            tool_resolver=self.tool_resolver,
            runtime_rbac_resolver=self.runtime_rbac_resolver,
        )
        self.collection_tool_resolver = CollectionToolResolver(self.session)
        settings = get_settings()
        self.mcp_credential_broker_enabled = bool(
            getattr(settings, "MCP_CREDENTIAL_BROKER_ENABLED", False)
        )
        self.runtime_credential_resolver = RuntimeCredentialResolver(
            self.credential_service,
            mcp_credential_broker_enabled=self.mcp_credential_broker_enabled,
        )
        self.data_instance_resolver = RuntimeDataInstanceResolver(
            session=self.session,
            instance_service=self.instance_service,
        )
        self.operation_resolver = RuntimeOperationResolver(
            operation_builder=self.operation_builder,
            collection_tool_resolver=self.collection_tool_resolver,
            credential_resolver=self.runtime_credential_resolver,
        )

    async def resolve(
        self,
        user_id: UUID,
        tenant_id: UUID,
        *,
        effective_permissions: Optional[EffectivePermissions] = None,
        default_collection_allow: bool = True,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        **_legacy_kwargs,
    ) -> OperationResolveResult:
        if effective_permissions is None:
            effective_permissions = await self.runtime_rbac_resolver.resolve_effective_permissions(
                user_id=user_id,
                tenant_id=tenant_id,
                default_collection_allow=default_collection_allow,
            )
        instances = await self.data_instance_resolver.resolve()

        result = OperationResolveResult(effective_permissions=effective_permissions)
        graph_builder = RuntimeExecutionGraphBuilder()
        for allowed in instances:
            instance = allowed.instance
            collection = allowed.collection
            provider = allowed.provider
            readiness_reason = allowed.readiness_reason
            runtime_domain = allowed.runtime_domain
            if readiness_reason != "ready":
                result.missing.collections.append(
                    f"{instance.slug} ({readiness_reason})"
                )
                continue

            if collection is None and has_collection_binding(instance.config):
                result.missing.collections.append(f"{instance.slug} (unresolved_collection_binding)")
                continue

            provider_for_execution = provider if provider is not None else instance
            binding = extract_collection_binding(instance.config)
            collection_id = str(binding.collection_id) if binding and binding.collection_id else None
            collection_slug = binding.collection_slug if binding else None
            if not self.runtime_rbac_resolver.is_collection_allowed(
                effective_permissions=effective_permissions,
                collection_slug=collection_slug,
            ):
                result.missing.collections.append(
                    f"{collection_slug or instance.slug} (rbac_denied)"
                )
                continue

            resolved_instance = self._build_resolved_data_instance(
                instance=instance,
                provider=provider,
                collection=collection,
                runtime_domain=runtime_domain,
                collection_id=collection_id,
                collection_slug=collection_slug,
            )
            result.resolved_data_instances.append(resolved_instance)

            operations = await self.operation_resolver.resolve_for_instance(
                instance=instance,
                provider=provider_for_execution,
                effective_permissions=effective_permissions,
                user_id=user_id,
                tenant_id=tenant_id,
                sandbox_overrides=sandbox_overrides,
            )
            if not operations:
                result.missing.tools.append(f"{instance.slug} (no operations)")
                continue

            for operation, credential_context in operations:
                result.resolved_operations.append(operation)
                context_payload = self._build_operation_context(
                    instance=instance,
                    provider_for_execution=provider_for_execution,
                    runtime_domain=runtime_domain,
                    operation=operation,
                )
                graph_builder.add_operation(
                    operation=operation,
                    context_payload=context_payload,
                    credential=credential_context,
                )

        result.execution_graph = graph_builder.build()
        return result

    @staticmethod
    def _build_resolved_data_instance(
        *,
        instance: ToolInstance,
        provider: Optional[ToolInstance],
        collection: Optional[Collection],
        runtime_domain: str,
        collection_id: Optional[str],
        collection_slug: Optional[str],
    ) -> ResolvedDataInstance:
        # LLM-facing description: prefer collection.description (curated asset doc)
        # and fall back to instance.description (provider-level blurb).
        description: Optional[str] = None
        entity_type: Optional[str] = None
        if collection is not None:
            description = collection.description or None
            entity_type = collection.entity_type or None
        if not description:
            description = instance.description or None
        return ResolvedDataInstance(
            instance_id=str(instance.id),
            slug=instance.slug,
            name=instance.name,
            domain=runtime_domain,
            collection_id=collection_id,
            collection_slug=collection_slug,
            placement=instance.placement,
            provider_instance_id=str(provider.id) if provider else None,
            provider_instance_slug=provider.slug if provider else None,
            description=description,
            entity_type=entity_type,
        )

    @staticmethod
    def _build_operation_context(
        *,
        instance: ToolInstance,
        provider_for_execution: ToolInstance,
        runtime_domain: str,
        operation: ResolvedOperation,
    ) -> Dict[str, Any]:
        return {
            "instance_id": str(instance.id),
            "instance_slug": instance.slug,
            "provider_instance_id": str(provider_for_execution.id),
            "provider_instance_slug": provider_for_execution.slug,
            "has_credentials": operation.target.has_credentials,
            "credential_scope": operation.credential_scope,
            "config": instance.config or {},
            "provider_config": provider_for_execution.config or {},
            "domain": runtime_domain,
            "data_instance_url": instance.url or None,
            "provider_url": provider_for_execution.url or None,
        }
