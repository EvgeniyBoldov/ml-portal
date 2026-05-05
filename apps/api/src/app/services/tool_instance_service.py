"""
ToolInstanceService v3 — управление инстансами платформы.

Instance v3 classification:
- instance_kind: data | service
- placement: local | remote
- domain: llm | mcp | collection.document | collection.table | rag | jira | netbox | dcbox

`domain` is transitional classification metadata.
Behavior checks should prefer explicit bindings (for example collection binding in config).
"""
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ToolInstanceNotFoundError,
    LocalInstanceProtectedError,
    InstanceInUseError,
    AppError as ToolInstanceError,
)
from app.core.logging import get_logger
from app.models.tool_instance import ToolInstance, InstancePlacement, InstanceKind
from app.models.collection import Collection
from app.repositories.tool_instance_repository import ToolInstanceRepository
from app.services.collection_linking import resolve_bound_collection_by_instance_id
from app.services.connector_templates import (
    normalize_data_connector_subtype,
    validate_connector_config,
)
from app.services.tool_instance.types import HealthCheckResult, RescanResult
from app.services.tool_instance.validation import ToolInstanceValidationService
from app.services.tool_instance.local_manager import ToolInstanceLocalManager
from app.services.tool_instance.health_service import ToolInstanceHealthService

logger = get_logger(__name__)
_UNSET = object()

# Backward-compat alias
InstanceType = InstancePlacement

class ToolInstanceService:
    """
    Сервис для управления ToolInstance v3.

    Отвечает за:
    - CRUD операции с инстансами (remote only через API)
    - Автоматическое управление локальными инстансами
    - Health check инстансов
    - Rescan инстансов
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ToolInstanceRepository(session)
        self.validation = ToolInstanceValidationService()
        self.local_manager = ToolInstanceLocalManager(self)
        self.health = ToolInstanceHealthService(self)

    LOCAL_TABLE_SERVICE_SLUG = "local-table-tools"
    LOCAL_DOCUMENT_SERVICE_SLUG = "local-document-tools"
    LOCAL_RUNTIME_SERVICE_SLUG = "local-runtime"
    SYSTEM_MANAGED_INSTANCE_SLUGS = {
        LOCAL_TABLE_SERVICE_SLUG,
        LOCAL_DOCUMENT_SERVICE_SLUG,
        LOCAL_RUNTIME_SERVICE_SLUG,
    }
    logger = logger

    @staticmethod
    def _infer_service_provider_kind(
        *,
        placement: str,
        domain: str,
        slug: str,
    ) -> Optional[str]:
        return ToolInstanceValidationService.infer_service_provider_kind(
            placement=placement,
            domain=domain,
            slug=slug,
            local_table_service_slug=ToolInstanceService.LOCAL_TABLE_SERVICE_SLUG,
            local_document_service_slug=ToolInstanceService.LOCAL_DOCUMENT_SERVICE_SLUG,
            local_runtime_service_slug=ToolInstanceService.LOCAL_RUNTIME_SERVICE_SLUG,
        )

    @classmethod
    def _normalize_config(
        cls,
        *,
        slug: str,
        instance_kind: str,
        placement: str,
        domain: str,
        config: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return ToolInstanceValidationService.normalize_config(
            slug=slug,
            instance_kind=instance_kind,
            placement=placement,
            domain=domain,
            config=config,
            local_table_service_slug=cls.LOCAL_TABLE_SERVICE_SLUG,
            local_document_service_slug=cls.LOCAL_DOCUMENT_SERVICE_SLUG,
            local_runtime_service_slug=cls.LOCAL_RUNTIME_SERVICE_SLUG,
        )

    @staticmethod
    def _validate_config_requirements(
        *,
        instance_kind: str,
        placement: str,
        url: str,
        config: Optional[Dict[str, Any]],
    ) -> None:
        ToolInstanceValidationService.validate_config_requirements(
            instance_kind=instance_kind,
            placement=placement,
            url=url,
            config=config,
        )

    @staticmethod
    def _validate_slug(slug: str) -> None:
        ToolInstanceValidationService.validate_slug(slug)

    @classmethod
    def _is_system_managed_instance(cls, instance: ToolInstance) -> bool:
        return ToolInstanceValidationService.is_system_managed_instance(
            instance,
            system_managed_slugs=cls.SYSTEM_MANAGED_INSTANCE_SLUGS,
        )

    @staticmethod
    def _validate_classification(instance_kind: str, placement: str) -> None:
        ToolInstanceValidationService.validate_classification(instance_kind, placement)

    async def _validate_access_link(
        self,
        *,
        connector_type: str,
        access_via_instance_id: Optional[UUID],
        current_instance_id: Optional[UUID] = None,
    ) -> None:
        await ToolInstanceValidationService.validate_access_link(
            repo=self.repo,
            connector_type=connector_type,
            access_via_instance_id=access_via_instance_id,
            current_instance_id=current_instance_id,
        )

    async def _resolve_bound_collection(self, instance: ToolInstance) -> Optional[Collection]:
        if not instance.is_data:
            return None
        return await resolve_bound_collection_by_instance_id(
            self.session,
            data_instance_id=instance.id,
        )

    async def evaluate_instance_readiness(self, instance: ToolInstance) -> tuple[bool, str, str]:
        """
        Evaluate runtime readiness of an instance.

        Returns:
            (is_ready, reason, semantic_source)
        semantic_source:
            - active_profile
            - derived_collection
            - none
        """
        if not instance.is_active:
            return False, "instance_inactive", "none"

        if instance.is_data:
            bound_collection = await self._resolve_bound_collection(instance)
            if bound_collection:
                return True, "ready", "derived_collection"

            if instance.access_via_instance_id:
                return True, "ready", "linked_provider"
            if instance.is_remote and (instance.url or "").strip():
                return True, "ready", "direct_remote"
            return False, "missing_access_binding", "none"

        # service instances
        if instance.is_remote and not (instance.url or "").strip():
            return False, "missing_provider_url", "none"
        return True, "ready", "none"

    # ─── Remote instance CRUD (API-facing) ────────────────────────────

    async def create_instance(
        self,
        slug: str,
        name: str,
        instance_kind: str = "data",
        connector_type: str = "data",
        connector_subtype: Optional[str] = None,
        placement: str = InstancePlacement.REMOTE.value,
        domain: str = "",
        url: str = "",
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        provider_kind: Optional[str] = None,
        access_via_instance_id: Optional[UUID] = None,
        allow_local: bool = False,
    ) -> ToolInstance:
        """Create a new tool instance."""
        self._validate_slug(slug)
        if instance_kind == InstanceKind.SERVICE.value and connector_type == "data":
            connector_type = "mcp"
        connector_type = ToolInstanceValidationService.normalize_connector_type(connector_type)
        connector_subtype = normalize_data_connector_subtype(
            connector_type=connector_type,
            connector_subtype=connector_subtype,
            legacy_domain=domain,
        )
        instance_kind = ToolInstanceValidationService.derive_instance_kind(connector_type)
        self._validate_classification(instance_kind, placement)

        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise ToolInstanceError(f"Instance with slug '{slug}' already exists")

        if placement == InstancePlacement.LOCAL.value and not allow_local:
            raise LocalInstanceProtectedError(
                "Local instances are managed by platform internals and cannot be created manually"
            )
        if placement == InstancePlacement.REMOTE.value and not (url or "").strip():
            raise ToolInstanceError("Remote instances require non-empty url")
        normalized_domain = str(domain or "").strip()
        if connector_type == "data":
            normalized_domain = connector_subtype or "api"
        elif connector_type == "mcp":
            normalized_domain = normalized_domain or "mcp"
        elif connector_type == "model":
            normalized_domain = normalized_domain or "llm"

        await self._validate_access_link(
            connector_type=connector_type,
            access_via_instance_id=access_via_instance_id,
            current_instance_id=None,
        )

        config_payload: Dict[str, Any] = dict(config or {})
        if provider_kind is not None:
            normalized_provider_kind = str(provider_kind).strip().lower()
            if not normalized_provider_kind:
                raise ToolInstanceError("provider_kind must be non-empty when provided")
            config_payload["provider_kind"] = normalized_provider_kind

        normalized_config = self._normalize_config(
            slug=slug,
            instance_kind=instance_kind,
            placement=placement,
            domain=normalized_domain,
            config=config_payload,
        )
        normalized_config = validate_connector_config(
            connector_type=connector_type,
            connector_subtype=connector_subtype,
            config=normalized_config,
        )
        self._validate_config_requirements(
            instance_kind=instance_kind,
            placement=placement,
            url=url if placement == InstancePlacement.REMOTE.value else "",
            config=normalized_config,
        )

        instance = ToolInstance(
            slug=slug,
            name=name,
            description=description,
            instance_kind=instance_kind,
            connector_type=connector_type,
            connector_subtype=connector_subtype,
            placement=placement,
            domain=normalized_domain,
            url=url if placement == InstancePlacement.REMOTE.value else "",
            config=normalized_config,
            access_via_instance_id=access_via_instance_id,
            is_active=True,
        )

        return await self.repo.create(instance)

    async def get_instance(self, instance_id: UUID) -> ToolInstance:
        """Get instance by ID"""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ToolInstanceNotFoundError(f"Instance '{instance_id}' not found")
        return instance

    async def update_instance(
        self,
        instance_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instance_kind: Optional[str] = None,
        connector_type: Optional[str] = None,
        connector_subtype: Optional[str] = None,
        domain: Optional[str] = None,
        url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        provider_kind: Optional[str] = None,
        is_active: Optional[bool] = None,
        access_via_instance_id: Any = _UNSET,
    ) -> ToolInstance:
        """Update tool instance."""
        instance = await self.get_instance(instance_id)
        if instance.is_local or self._is_system_managed_instance(instance):
            raise LocalInstanceProtectedError(
                "System-managed instances are managed by platform internals and cannot be updated manually"
            )

        if connector_type is None and instance_kind is not None:
            inferred = "mcp"
            connector_type = inferred if instance_kind == InstanceKind.SERVICE.value else "data"
        next_connector_type = (
            ToolInstanceValidationService.normalize_connector_type(connector_type)
            if connector_type is not None
            else instance.connector_type
        )
        subtype_candidate = (
            connector_subtype
            if connector_subtype is not None
            else (instance.connector_subtype if next_connector_type == "data" else None)
        )
        next_connector_subtype = normalize_data_connector_subtype(
            connector_type=next_connector_type,
            connector_subtype=subtype_candidate,
            legacy_domain=(domain if domain is not None else instance.domain),
        )
        next_kind = ToolInstanceValidationService.derive_instance_kind(next_connector_type)
        next_domain = domain if domain is not None else instance.domain
        if next_connector_type == "data":
            next_domain = next_connector_subtype or "api"
        elif next_connector_type == "mcp":
            next_domain = next_domain or "mcp"
        elif next_connector_type == "model":
            next_domain = next_domain or "llm"
        next_url = url if url is not None else instance.url
        next_access_via = (
            access_via_instance_id
            if access_via_instance_id is not _UNSET
            else instance.access_via_instance_id
        )

        self._validate_classification(next_kind, instance.placement)
        if instance.placement == InstancePlacement.REMOTE.value and not (next_url or "").strip():
            raise ToolInstanceError("Remote instances require non-empty url")
        await self._validate_access_link(
            connector_type=next_connector_type,
            access_via_instance_id=next_access_via,
            current_instance_id=instance.id,
        )

        next_config: Dict[str, Any] = dict(config if config is not None else (instance.config or {}))
        if provider_kind is not None:
            normalized_provider_kind = str(provider_kind).strip().lower()
            if not normalized_provider_kind:
                raise ToolInstanceError("provider_kind must be non-empty when provided")
            next_config["provider_kind"] = normalized_provider_kind
        normalized_config = self._normalize_config(
            slug=instance.slug,
            instance_kind=next_kind,
            placement=instance.placement,
            domain=next_domain,
            config=next_config,
        )
        normalized_config = validate_connector_config(
            connector_type=next_connector_type,
            connector_subtype=next_connector_subtype,
            config=normalized_config,
        )
        self._validate_config_requirements(
            instance_kind=next_kind,
            placement=instance.placement,
            url=next_url if instance.placement == InstancePlacement.REMOTE.value else "",
            config=normalized_config,
        )

        if name is not None:
            instance.name = name
        if description is not None:
            instance.description = description
        if url is not None:
            instance.url = url
        if config is not None or normalized_config != instance.config:
            instance.config = normalized_config
        # Track is_active change for discovered tool invalidation
        is_active_changed = False
        if is_active is not None:
            is_active_changed = instance.is_active != is_active
            instance.is_active = is_active

        connector_type_changed = connector_type is not None
        if connector_type_changed:
            instance.connector_type = next_connector_type
        if connector_subtype is not None or connector_type_changed:
            instance.connector_subtype = next_connector_subtype
        if instance_kind is not None or connector_type is not None:
            instance.instance_kind = next_kind
        if domain is not None or connector_type is not None or connector_subtype is not None:
            instance.domain = next_domain
        if access_via_instance_id is not _UNSET:
            instance.access_via_instance_id = access_via_instance_id

        instance.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        
        # Invalidate discovered tools if MCP connector was deactivated
        if is_active_changed and not instance.is_active and instance.connector_type == "mcp":
            await self._invalidate_discovered_tools(instance.id)
        
        return await self.repo.update(instance)

    async def delete_instance(self, instance_id: UUID) -> None:
        """Delete tool instance with validation."""
        instance = await self.get_instance(instance_id)
        if instance.is_local or self._is_system_managed_instance(instance):
            raise LocalInstanceProtectedError(
                "System-managed instances are managed by platform internals and cannot be deleted manually"
            )
        await self.repo.delete(instance)
    
    async def _invalidate_discovered_tools(self, instance_id: UUID) -> None:
        """Mark all discovered tools from an MCP provider as inactive."""
        from sqlalchemy import update
        from app.models.discovered_tool import DiscoveredTool
        
        stmt = (
            update(DiscoveredTool)
            .where(DiscoveredTool.provider_instance_id == str(instance_id))
            .values(is_active=False)
        )
        await self.session.execute(stmt)
        logger.info(f"Invalidated discovered tools for MCP provider {instance_id}")

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        instance_kind: Optional[str] = None,
        connector_type: Optional[str] = None,
        connector_subtype: Optional[str] = None,
        placement: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        return await self.repo.list_instances(
            skip=skip,
            limit=limit,
            is_active=is_active,
            instance_kind=instance_kind,
            connector_type=connector_type,
            connector_subtype=connector_subtype,
            placement=placement,
            domain=domain,
        )

    # ─── Instance resolution ────────────────────────────────────────────

    async def resolve_instance(
        self,
        tool_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ToolInstance]:
        """Resolve instance by slug."""
        instance = await self.repo.get_by_slug(tool_slug)
        if instance and instance.is_active:
            return instance
        return None

    # ─── Local instance management (internal) ─────────────────────────

    async def create_local_instance(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        domain: str = "rag",
        instance_kind: str = "data",
        connector_type: str = "data",
        connector_subtype: Optional[str] = None,
        access_via_instance_id: Optional[UUID] = None,
    ) -> ToolInstance:
        """Create a LOCAL instance (internal use only, not exposed via API)."""
        instance = await self.create_instance(
            slug=slug,
            name=name,
            description=description,
            instance_kind=instance_kind,
            connector_type=connector_type,
            connector_subtype=connector_subtype,
            placement=InstancePlacement.LOCAL.value,
            domain=domain,
            url="",
            config=config,
            access_via_instance_id=access_via_instance_id,
            allow_local=True,
        )
        instance.health_status = "healthy"
        instance.is_active = True
        result = await self.repo.update(instance)
        logger.info(f"Created local instance: {slug} (domain: {domain})")
        return result

    async def _ensure_local_service_instance(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        domain: str,
        provider_kind: str,
    ) -> tuple[ToolInstance, bool, bool]:
        return await self.local_manager.ensure_local_service_instance(
            slug=slug,
            name=name,
            description=description,
            domain=domain,
            provider_kind=provider_kind,
        )

    async def ensure_local_service_instances(self) -> tuple[ToolInstance, ToolInstance, int, int]:
        table_instance, table_created, table_updated = await self._ensure_local_service_instance(
            slug=self.LOCAL_TABLE_SERVICE_SLUG,
            name="Local Table Tools",
            description="Built-in provider for local table collections and structured local assets",
            domain="collection.table",
            provider_kind="local_tables",
        )
        document_instance, document_created, document_updated = await self._ensure_local_service_instance(
            slug=self.LOCAL_DOCUMENT_SERVICE_SLUG,
            name="Local Document Tools",
            description="Built-in provider for local document collections and document retrieval",
            domain="collection.document",
            provider_kind="local_documents",
        )
        return (
            table_instance,
            document_instance,
            int(table_created) + int(document_created),
            int(table_updated) + int(document_updated),
        )

    async def resolve_local_service_for_collection_type(self, collection_type: str) -> ToolInstance:
        table_instance, document_instance, _, _ = await self.ensure_local_service_instances()
        if collection_type == "document":
            return document_instance
        return table_instance

    async def delete_local_instance(self, instance_id: UUID) -> None:
        """Delete a LOCAL instance (internal use only)."""
        instance = await self.get_instance(instance_id)
        await self.repo.delete(instance)
        logger.info(f"Deleted local instance: {instance.slug}")

    # ─── Health check ─────────────────────────────────────────────────

    async def check_health(self, instance_id: UUID) -> HealthCheckResult:
        """Perform health check on a tool instance."""
        return await self.health.check_health(instance_id)

    async def _perform_health_check(self, instance: ToolInstance) -> HealthCheckResult:
        """Perform actual health check using instance url."""
        return await self.health.perform_health_check(instance)

    # ─── Rescan ───────────────────────────────────────────────────────

    async def rescan_local_instances(self) -> RescanResult:
        """
        Rescan and sync local instances with actual data.

        - Ensures canonical local SERVICE instances exist
        - Rebinds local collections to canonical services
        - Removes legacy local DATA instances (rag-global / collection-*)
        """
        from sqlalchemy import select
        from app.models.collection import Collection

        result = RescanResult()

        try:
            table_service, document_service, service_created, service_updated = await self.ensure_local_service_instances()
            result.created += service_created
            result.updated += service_updated

            # 1. Rebind local collections to canonical service instances.
            collections_stmt = select(Collection).where(Collection.is_active == True)  # noqa: E712
            collections_result = await self.session.execute(collections_stmt)
            all_collections = list(collections_result.scalars().all())
            collections = [
                c
                for c in all_collections
                if not (
                    c.collection_type == "sql"
                    or c.collection_type == "api"
                    or
                    isinstance(c.source_contract, dict)
                    and str(c.source_contract.get("mode", "")).lower() == "remote"
                )
            ]

            for coll in collections:
                target_service = (
                    document_service if coll.collection_type == "document" else table_service
                )
                if coll.data_instance_id != target_service.id:
                    coll.data_instance_id = target_service.id
                    await self.session.flush()
                    result.updated += 1

            # 2. Remove legacy local DATA instances that were previously auto-created.
            existing_data_instances, _ = await self.repo.list_instances(
                placement=InstancePlacement.LOCAL.value,
                instance_kind=InstanceKind.DATA.value,
                limit=10000,
            )
            for inst in existing_data_instances:
                if inst.slug == "rag-global" or inst.slug.startswith("collection-"):
                    await self.repo.delete(inst)
                    result.deleted += 1
                    logger.info("Removed legacy local data instance: %s", inst.slug)

        except Exception as e:
            logger.error(f"Rescan failed: {e}")
            result.errors += 1

        logger.info(
            f"Rescan complete: created={result.created}, "
            f"updated={result.updated}, deleted={result.deleted}, "
            f"errors={result.errors}"
        )
        return result
