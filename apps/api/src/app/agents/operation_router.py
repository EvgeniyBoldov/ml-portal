from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import (
    MissingRequirements,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.collection_readiness import CollectionReadinessBuilder
from app.agents.data_instance_resolver import RuntimeDataInstanceResolver
from app.agents.credential_resolver import RuntimeCredentialResolver
from app.agents.operation_resolver import RuntimeOperationResolver
from app.agents.operation_builder import OperationBuilder
from app.agents.runtime_graph import RuntimeExecutionGraph
from app.agents.runtime_graph_builder import RuntimeExecutionGraphBuilder
from app.agents.capability_resolver import CollectionCapabilityResolver, SystemCapabilityResolver
from app.agents.runtime.published_capabilities import attach_published_operation_summaries
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.tool_resolver import ToolResolver
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType
from app.models.tool_instance import ToolInstance
from app.services.credential_service import CredentialService
from app.services.permission_service import EffectivePermissions, PermissionService
from app.services.tool_instance_service import ToolInstanceService
from app.services.collection_tool_resolver import CollectionToolResolver
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService
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
        self.collection_capability_resolver = CollectionCapabilityResolver(self.collection_tool_resolver)
        self.system_capability_resolver = SystemCapabilityResolver(self.collection_tool_resolver)
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
            collection_capability_resolver=self.collection_capability_resolver,
            credential_resolver=self.runtime_credential_resolver,
        )
        self.collection_status_snapshot = CollectionStatusSnapshotService(self.session)
        self.collection_readiness_builder = CollectionReadinessBuilder(
            schema_stale_after_hours=getattr(settings, "COLLECTION_SCHEMA_STALE_HOURS", 24)
        )

    async def resolve(
        self,
        user_id: UUID,
        tenant_id: UUID,
        *,
        effective_permissions: Optional[EffectivePermissions] = None,
        default_collection_allow: bool = True,
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
        seen_operation_slugs: set[str] = set()
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

            if collection is None:
                result.missing.collections.append(f"{instance.slug} (unbound_data_instance)")
                continue

            provider_for_execution = provider if provider is not None else instance
            collection_id = str(collection.id)
            collection_slug = str(collection.slug)
            status_snapshot = await self.collection_status_snapshot.get_status_snapshot(collection)
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
                readiness=None,
            )
            result.resolved_data_instances.append(resolved_instance)

            operations = await self.operation_resolver.resolve_for_instance(
                instance=instance,
                provider=provider_for_execution,
                runtime_domain=runtime_domain,
                effective_permissions=effective_permissions,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            readiness = self.collection_readiness_builder.build(
                collection=collection,
                data_instance=instance,
                provider_instance=provider_for_execution,
                operations=[item[0] for item in operations],
                collection_snapshot=status_snapshot,
            )
            resolved_instance.readiness = readiness
            if readiness.credential_status == "missing":
                result.missing.credentials.append(instance.slug)
            if not operations:
                result.missing.tools.append(f"{instance.slug} (no operations)")
                continue

            for operation, credential_context in operations:
                if operation.operation_slug in seen_operation_slugs:
                    # Shared local service instance handles multiple collections;
                    # aggregate the collection into the existing binding.
                    existing = graph_builder._graph.bindings.get(operation.operation_slug)
                    if existing and collection_slug:
                        current = set(existing.context.allowed_collection_slugs or [])
                        current.add(collection_slug)
                        existing.context.allowed_collection_slugs = sorted(current)
                    continue
                seen_operation_slugs.add(operation.operation_slug)
                if operation.collection_slug is None and collection_slug:
                    operation.collection_slug = collection_slug
                result.resolved_operations.append(operation)
                context_payload = self._build_operation_context(
                    instance=instance,
                    provider_for_execution=provider_for_execution,
                    scope=operation.scope,
                    runtime_domain=runtime_domain,
                    collection_id=collection_id,
                    collection_slug=collection_slug,
                    allowed_collection_slugs=[collection_slug] if collection_slug else [],
                    has_credentials=operation.target.has_credentials,
                    credential_scope=operation.credential_scope,
                )
                graph_builder.add_operation(
                    operation=operation,
                    context_payload=context_payload,
                    credential=credential_context,
                )

        # System tools (file.*) must be available even when no data instances exist.
        await self._resolve_system_tools(
            result=result,
            graph_builder=graph_builder,
            seen_operation_slugs=seen_operation_slugs,
            effective_permissions=effective_permissions,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        attach_published_operation_summaries(
            result.resolved_operations,
            result.resolved_data_instances,
        )
        result.execution_graph = graph_builder.build()
        return result

    async def _resolve_system_tools(
        self,
        *,
        result: OperationResolveResult,
        graph_builder: RuntimeExecutionGraphBuilder,
        seen_operation_slugs: set[str],
        effective_permissions: Optional[EffectivePermissions],
        user_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Load global system tools and append to resolved operations."""
        from types import SimpleNamespace

        system_capabilities = await self.system_capability_resolver.resolve()
        if not system_capabilities:
            return

        dummy = SimpleNamespace(
            id="system",
            slug="system",
            name="System",
            domain="system",
            url=None,
            config={},
            is_local=True,
            health_status="healthy",
        )

        for capability in system_capabilities:
            discovered_tool = capability.discovered_tool
            if str(getattr(discovered_tool, "slug", "") or "") in seen_operation_slugs:
                continue
            built = await self.operation_builder._build_single_operation(
                capability=capability,
                instance=dummy,
                provider=dummy,
                has_credentials=True,
                runtime_domain="system",
                context_domains=["system"],
                effective_permissions=effective_permissions,
                user_id=user_id,
                tenant_id=tenant_id,
                seen_operation_slugs=seen_operation_slugs,
                resolve_execution_credentials=self.operation_resolver._resolve_execution_credentials,
            )
            if built is None:
                continue
            operation, credential_context = built
            result.resolved_operations.append(operation)
            context_payload = self._build_operation_context(
                instance=dummy,
                provider_for_execution=dummy,
                scope=operation.scope,
                runtime_domain="system",
                collection_id=None,
                collection_slug=None,
                allowed_collection_slugs=[],
                has_credentials=operation.target.has_credentials,
                credential_scope=operation.credential_scope,
            )
            graph_builder.add_operation(
                operation=operation,
                context_payload=context_payload,
                credential=credential_context,
            )

    @staticmethod
    def _build_resolved_data_instance(
        *,
        instance: ToolInstance,
        provider: Optional[ToolInstance],
        collection: Optional[Collection],
        runtime_domain: str,
        collection_id: Optional[str],
        collection_slug: Optional[str],
        readiness: Optional[Any],
    ) -> ResolvedDataInstance:
        # LLM-facing description: prefer collection.description (curated asset doc)
        # and fall back to instance.description (provider-level blurb).
        description: Optional[str] = None
        entity_type: Optional[str] = None
        collection_type: Optional[str] = None
        data_description: Optional[str] = None
        usage_purpose: Optional[str] = None
        usage_rules: Optional[str] = None
        remote_tables: List[str] = []
        if collection is not None:
            description = collection.description or None
            entity_type = collection.entity_type or None
            collection_type = (
                str(collection.collection_type).strip()
                if getattr(collection, "collection_type", None)
                else None
            )
            if collection_type == CollectionType.SQL.value:
                remote_tables = _extract_remote_table_names(
                    table_schema=collection.table_schema if isinstance(collection.table_schema, dict) else {},
                    source_contract=collection.source_contract if isinstance(collection.source_contract, dict) else {},
                )
            current_version = getattr(collection, "current_version", None)
            if current_version is not None:
                data_description = getattr(current_version, "data_description", None) or None
                usage_purpose = getattr(current_version, "usage_purpose", None) or None
                usage_rules = getattr(current_version, "usage_rules", None) or None
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
            collection_type=collection_type,
            data_description=data_description,
            usage_purpose=usage_purpose,
            usage_rules=usage_rules,
            remote_tables=remote_tables,
            readiness=readiness,
        )

    @staticmethod
    def _build_operation_context(
        *,
        instance: ToolInstance,
        provider_for_execution: ToolInstance,
        scope: str,
        runtime_domain: str,
        collection_id: Optional[str],
        collection_slug: Optional[str],
        allowed_collection_slugs: list[str],
        has_credentials: bool,
        credential_scope: str,
    ) -> Dict[str, Any]:
        return {
            "instance_id": str(instance.id),
            "instance_slug": instance.slug,
            "scope": scope,
            "collection_id": collection_id,
            "collection_slug": collection_slug,
            "allowed_collection_slugs": allowed_collection_slugs,
            "provider_instance_id": str(provider_for_execution.id),
            "provider_instance_slug": provider_for_execution.slug,
            "has_credentials": has_credentials,
            "credential_scope": credential_scope,
            "config": instance.config or {},
            "provider_config": provider_for_execution.config or {},
            "domain": runtime_domain,
            "data_instance_url": instance.url or None,
            "provider_url": provider_for_execution.url or None,
        }


def _extract_remote_table_names(
    *,
    table_schema: Dict[str, Any],
    source_contract: Dict[str, Any],
) -> List[str]:
    names: List[str] = []
    seen: set[str] = set()

    def _push(raw_name: Any) -> None:
        name = str(raw_name or "").strip()
        if not name:
            return
        if name in seen:
            return
        seen.add(name)
        names.append(name)

    for source in (table_schema, source_contract):
        tables = source.get("tables")
        if isinstance(tables, list):
            for item in tables:
                if isinstance(item, str):
                    _push(item)
                elif isinstance(item, dict):
                    _push(item.get("name") or item.get("table"))

        schemas = source.get("schemas")
        if isinstance(schemas, list):
            for schema_obj in schemas:
                if not isinstance(schema_obj, dict):
                    continue
                schema_tables = schema_obj.get("tables")
                if not isinstance(schema_tables, list):
                    continue
                for item in schema_tables:
                    if isinstance(item, str):
                        _push(item)
                    elif isinstance(item, dict):
                        _push(item.get("name") or item.get("table"))
        elif isinstance(schemas, dict):
            for schema_tables in schemas.values():
                if not isinstance(schema_tables, list):
                    continue
                for item in schema_tables:
                    if isinstance(item, str):
                        _push(item)
                    elif isinstance(item, dict):
                        _push(item.get("name") or item.get("table"))

    return names
