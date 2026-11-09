from __future__ import annotations

from typing import Awaitable, Callable, List, Optional
from uuid import UUID

from app.agents.capability_resolver import CapabilityCandidate
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget, ResolvedOperation
from app.agents.credential_resolver import CredentialsUnavailableError
from app.agents.runtime.prompt_contract import build_prompt_input_schema, summarize_prompt_input_schema
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.tool_resolver import ResolvedTool, ToolResolver
from app.core.logging import get_logger
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_instance import ToolInstance
from app.services.permission_service import EffectivePermissions
from app.services.sandbox_override_resolver import SandboxToolOverrides

logger = get_logger(__name__)

# Virtual collection operations have no discovered_tools row to carry the
# persisted policy. Keep list and grouped-row operations on the Store path.
_VIRTUAL_STORE_RESULT_SLUGS = frozenset({
    "collection.search",
    "collection.aggregate",
    "collection.table.search",
    "collection.table.aggregate",
})


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
        sandbox_tool_overrides: Optional[SandboxToolOverrides] = None,
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
                sandbox_tool_overrides=sandbox_tool_overrides,
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
        sandbox_tool_overrides: Optional[SandboxToolOverrides] = None,
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
            sandbox_tool_overrides=sandbox_tool_overrides,
        )
        if resolution is None:
            return None
        operation_name = resolution.operation_name
        is_system_tool = capability.scope_kind == "system"
        operation_slug = operation_name
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
        # Credential ownership is selected only from the effective platform
        # risk classification. Side-effect/confirmation descriptors do not
        # grant MCP servers authority over credential owner scope.
        operation_is_risky = resolution.risk_level != "safe"
        credential_policy = (
            "not_required" if instance.is_local
            else "user_only" if operation_is_risky
            else "user_tenant_platform"
        )
        if provider_type == "mcp" and not instance.is_local:
            if user_id is not None and tenant_id is not None:
                # The data source owns upstream credentials. MCP is an
                # unauthenticated transport endpoint and is never a fallback.
                try:
                    credential_context = await resolve_execution_credentials(
                        instance,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        tool_slug=operation_slug,
                        operation=operation_name,
                        is_risky=operation_is_risky,
                    )
                except CredentialsUnavailableError as exc:
                    logger.info(
                        "operation_skipped_missing_data_credentials",
                        extra={
                            "operation_slug": operation_slug,
                            "instance_slug": instance.slug,
                            "scope_required": exc.scope_required,
                        },
                    )
            logger.info(
                "operation_credential_binding_built operation=%s data_instance_id=%s provider_instance_id=%s "
                "credential_present=%s credential_id=%s owner_type=%s auth_type=%s policy=%s risk_level=%s",
                operation_slug, instance.id, provider_for_target.id,
                credential_context is not None,
                credential_context.credential_id if credential_context else "-",
                credential_context.owner_type if credential_context else "-",
                credential_context.auth_type if credential_context else "-",
                credential_policy, resolution.risk_level,
                extra={
                    "operation_slug": operation_slug,
                    "data_instance_id": str(instance.id),
                    "provider_instance_id": str(provider_for_target.id),
                    "credential_present": credential_context is not None,
                    "credential_id": credential_context.credential_id if credential_context else None,
                    "credential_owner_type": credential_context.owner_type if credential_context else None,
                    "credential_auth_type": credential_context.auth_type if credential_context else None,
                    "credential_policy": credential_policy,
                    "risk_level": resolution.risk_level,
                },
            )
            resolved_has_credentials = credential_context is not None
            if not credential_context:
                logger.info(
                    "operation_no_credentials_proceeding",
                    extra={
                        "instance_slug": instance.slug,
                        "raw_slug": raw_operation_name,
                        "canonical_operation": operation_name,
                        "credential_policy": credential_policy,
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
            credential_policy=credential_policy if provider_type == "mcp" else "not_required",
            health_status=provider_for_target.health_status or instance.health_status,
        )
        discovered_tool_id = str(getattr(discovered_tool, "id", "") or "") or None
        result_delivery = getattr(discovered_tool, "result_delivery", None)
        if operation_slug.startswith("result."):
            # Workspace tools own their established result/presentation
            # semantics; the discovered-tool policy is for source tools.
            result_delivery = None
        elif not discovered_tool_id and raw_operation_name in _VIRTUAL_STORE_RESULT_SLUGS:
            result_delivery = "store"

        operation = ResolvedOperation(
            operation_slug=operation_slug,
            operation=operation_name,
            name=resolution.title,
            scope="system" if is_system_tool else "collection",
            description=resolution.description,
            discovery_description=str(getattr(discovered_tool, "description", None) or "").strip() or None,
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
            resource=None,
            systems=[],
            risk_flags=list(resolution.risk_flags),
            raw_tool_slug=raw_operation_name,
            discovered_tool_id=discovered_tool_id,
            published_domain=resolution.domain,
            result_kind=resolution.result_kind,
            result_delivery=(result_delivery if result_delivery is not None else
                             (None if operation_slug.startswith("result.") else "direct")),
            observed_data_schema=getattr(discovered_tool, "observed_data_schema", None),
            sandbox_override_snapshot=getattr(resolution, "sandbox_override_snapshot", {}),
            input_schema_summary=[],
            target=target,
        )
        operation.input_schema_summary = summarize_prompt_input_schema(build_prompt_input_schema(operation))
        return operation, credential_context
