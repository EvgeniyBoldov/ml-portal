from __future__ import annotations

from typing import Awaitable, Callable, List, Optional
from uuid import UUID

from app.agents.capability_resolver import CapabilityCandidate
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget, ResolvedOperation
from app.agents.operation_publication import build_runtime_operation_slug
from app.agents.runtime.prompt_contract import build_prompt_input_schema, summarize_prompt_input_schema
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.tool_resolver import ResolvedTool, ToolResolver
from app.core.logging import get_logger
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.permission_service import EffectivePermissions

logger = get_logger(__name__)


class OperationBuilder:
    """Build runtime operations for data/provider instance pair."""

    def __init__(
        self,
        *,
        tool_resolver: ToolResolver,
        runtime_rbac_resolver: RuntimeRbacResolver,
    ) -> None:
        self.tool_resolver = tool_resolver
        self.runtime_rbac_resolver = runtime_rbac_resolver

    async def build_operations_for_instance(
        self,
        *,
        instance: ToolInstance,
        provider: ToolInstance,
        runtime_domain: str,
        context_domains: Optional[List[str]],
        has_credentials: Optional[bool] = None,
        effective_permissions: Optional[EffectivePermissions] = None,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        capability_candidates: List[CapabilityCandidate],
        resolve_execution_credentials: Callable[..., Awaitable[Optional[OperationCredentialContext]]],
    ) -> List[tuple[ResolvedOperation, Optional[OperationCredentialContext]]]:
        operations: List[tuple[ResolvedOperation, Optional[OperationCredentialContext]]] = []
        seen_operation_slugs: set[str] = set()
        for capability in capability_candidates:
            built = await self._build_single_operation(
                capability=capability,
                instance=instance,
                provider=provider,
                has_credentials=has_credentials,
                runtime_domain=runtime_domain,
                context_domains=context_domains,
                effective_permissions=effective_permissions,
                user_id=user_id,
                tenant_id=tenant_id,
                seen_operation_slugs=seen_operation_slugs,
                resolve_execution_credentials=resolve_execution_credentials,
            )
            if built is not None:
                operations.append(built)
        return operations

    async def _build_single_operation(
        self,
        *,
        capability: CapabilityCandidate,
        instance: ToolInstance,
        provider: ToolInstance,
        has_credentials: Optional[bool],
        runtime_domain: str,
        context_domains: Optional[List[str]],
        effective_permissions: Optional[EffectivePermissions],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        seen_operation_slugs: set[str],
        resolve_execution_credentials: Callable[..., Awaitable[Optional[OperationCredentialContext]]],
    ) -> Optional[tuple[ResolvedOperation, Optional[OperationCredentialContext]]]:
        discovered_tool = capability.discovered_tool
        raw_operation_name = str(getattr(discovered_tool, "slug", "") or "")
        if not raw_operation_name.strip():
            return None

        resolution: Optional[ResolvedTool] = await self.tool_resolver.resolve(
            discovered_tool=discovered_tool,
            instance=instance,
            provider=provider,
            runtime_domain=runtime_domain,
            context_domains=context_domains,
        )
        if resolution is None:
            return None
        publication = resolution.publication
        if publication is None:
            logger.info(
                "operation_builder_skip_unpublished_tool",
                extra={
                    "instance_slug": instance.slug,
                    "instance_domain": runtime_domain,
                    "raw_slug": raw_operation_name,
                },
            )
            return None
        operation_name = publication.canonical_op_slug

        is_system_tool = publication.scope_kind == "system"
        if is_system_tool:
            operation_slug = operation_name
        else:
            operation_slug = build_runtime_operation_slug(instance.slug, operation_name)
        if operation_slug in seen_operation_slugs:
            logger.info(
                "operation_publication_duplicate_canonical_skipped",
                extra={
                    "instance_slug": instance.slug,
                    "raw_slug": raw_operation_name,
                    "operation_slug": operation_slug,
                },
            )
            return None
        seen_operation_slugs.add(operation_slug)

        provider_type = "mcp" if discovered_tool.source == "mcp" else "local"
        provider_for_target = provider if provider_type == "mcp" else instance

        credential_context = None
        resolved_has_credentials = True if provider_type == "local" else provider_for_target.is_local
        if provider_type == "mcp" and provider_for_target.is_remote:
            if user_id is not None and tenant_id is not None:
                # For MCP providers: credentials belong to the data instance (e.g. netbox-inventory-data),
                # not the MCP service instance. Try data instance first, fall back to provider.
                credential_instance = instance if provider_type == "mcp" else provider_for_target
                credential_context = await resolve_execution_credentials(
                    credential_instance,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tool_slug=operation_slug,
                    operation=operation_name,
                    credential_scope=resolution.credential_scope,
                    risk_level=resolution.risk_level,
                    side_effects=resolution.side_effects,
                    requires_confirmation=resolution.requires_confirmation,
                )
                _credentials_source = "data" if credential_context is not None else None
                if credential_context is None and provider_type == "mcp":
                    credential_context = await resolve_execution_credentials(
                        provider_for_target,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        tool_slug=operation_slug,
                        operation=operation_name,
                        credential_scope=resolution.credential_scope,
                        risk_level=resolution.risk_level,
                        side_effects=resolution.side_effects,
                        requires_confirmation=resolution.requires_confirmation,
                    )
                    if credential_context is not None:
                        _credentials_source = "provider"
                if _credentials_source:
                    logger.info(
                        "credentials_resolution_source",
                        extra={
                            "operation_slug": operation_slug,
                            "source": _credentials_source,
                            "instance_slug": instance.slug,
                            "provider_slug": provider_for_target.slug,
                        },
                    )
            resolved_has_credentials = credential_context is not None or provider_for_target.is_local
            if not credential_context:
                logger.info(
                    "operation_no_credentials_proceeding",
                    extra={
                        "instance_slug": instance.slug,
                        "raw_slug": raw_operation_name,
                        "canonical_operation": operation_name,
                        "credential_scope": resolution.credential_scope,
                    },
                )
        elif has_credentials is not None:
            resolved_has_credentials = has_credentials
        # System tools are global — they do not belong to a specific collection,
        # but ProviderExecutionTarget still requires a non-empty data-instance
        # identity. Use a stable sentinel so graph/trace code can keep working
        # without fabricating a real collection binding.
        if is_system_tool:
            data_instance_id = "system"
            data_instance_slug = "system"
        else:
            data_instance_id = str(instance.id)
            data_instance_slug = instance.slug

        target = ProviderExecutionTarget(
            operation_slug=operation_slug,
            provider_type=provider_type,
            provider_instance_id=str(provider_for_target.id),
            provider_instance_slug=provider_for_target.slug,
            provider_url=provider_for_target.url or None,
            data_instance_id=data_instance_id,
            data_instance_slug=data_instance_slug,
            handler_slug=raw_operation_name if provider_type == "local" else None,
            mcp_tool_name=raw_operation_name if provider_type == "mcp" else None,
            timeout_s=None,
            has_credentials=resolved_has_credentials,
            health_status=provider_for_target.health_status or instance.health_status,
        )
        operation = ResolvedOperation(
            operation_slug=operation_slug,
            operation=operation_name,
            name=resolution.title,
            scope="system" if is_system_tool else "collection",
            description=resolution.description,
            input_schema=resolution.input_schema,
            output_schema=resolution.output_schema,
            data_instance_id=data_instance_id,
            data_instance_slug=data_instance_slug,
            provider_instance_id=str(provider_for_target.id),
            provider_instance_slug=provider_for_target.slug,
            source=provider_type,
            risk_level=resolution.risk_level,
            side_effects=resolution.side_effects,
            idempotent=resolution.idempotent,
            requires_confirmation=resolution.requires_confirmation,
            credential_scope=resolution.credential_scope,
            resource=None,
            systems=[],
            risk_flags=list(resolution.risk_flags),
            raw_tool_slug=raw_operation_name,
            published_domain=resolution.domain,
            result_kind=resolution.result_kind,
            input_schema_summary=[],
            target=target,
        )
        operation.input_schema_summary = summarize_prompt_input_schema(build_prompt_input_schema(operation))
        return operation, credential_context
