"""
ToolInstanceService v3 - управление инстансами инструментов.

Instance types:
- LOCAL: auto-managed (RAG, collections). Cannot be created/deleted via API.
- REMOTE: user-managed (jira, netbox, crm). Full CRUD via API.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool_instance import ToolInstance, InstanceType
from app.repositories.tool_instance_repository import ToolInstanceRepository

logger = get_logger(__name__)


class ToolInstanceError(Exception):
    pass


class ToolInstanceNotFoundError(ToolInstanceError):
    pass


class LocalInstanceProtectedError(ToolInstanceError):
    """Raised when trying to manually create/delete a local instance."""
    pass


@dataclass
class HealthCheckResult:
    """Result of health check"""
    status: str  # "healthy" | "unhealthy" | "unknown"
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class RescanResult:
    """Result of instance rescan"""
    created: int = 0
    updated: int = 0
    deleted: int = 0
    errors: int = 0


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

    # ─── Remote instance CRUD (API-facing) ────────────────────────────

    async def create_instance(
        self,
        tool_group_id: UUID,
        slug: str,
        name: str,
        url: str,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None,
    ) -> ToolInstance:
        """Create a new REMOTE tool instance. Local instances are auto-managed."""
        instance = ToolInstance(
            tool_group_id=tool_group_id,
            slug=slug,
            name=name,
            url=url,
            description=description,
            config=config,
            category=category,
            instance_type=InstanceType.REMOTE.value,
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
        url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        category: Optional[str] = None,
    ) -> ToolInstance:
        """Update tool instance. Local instances can only update is_active."""
        instance = await self.get_instance(instance_id)

        if instance.instance_type == InstanceType.LOCAL.value:
            # Local instances: only allow toggling is_active
            if any(v is not None for v in [name, description, url, config]):
                raise LocalInstanceProtectedError(
                    "Local instances cannot be modified. Only is_active can be toggled."
                )
            if is_active is not None:
                instance.is_active = is_active
        else:
            if name is not None:
                instance.name = name
            if description is not None:
                instance.description = description
            if url is not None:
                instance.url = url
            if config is not None:
                instance.config = config
            if is_active is not None:
                instance.is_active = is_active
            if category is not None:
                instance.category = category

        return await self.repo.update(instance)

    async def delete_instance(self, instance_id: UUID) -> None:
        """Delete a REMOTE tool instance. Local instances cannot be deleted via API."""
        instance = await self.get_instance(instance_id)
        if instance.instance_type == InstanceType.LOCAL.value:
            raise LocalInstanceProtectedError(
                "Local instances cannot be deleted manually. "
                "They are managed automatically by the backend."
            )
        await self.repo.delete(instance)

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        tool_group_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
        instance_type: Optional[str] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        return await self.repo.list_instances(
            skip=skip,
            limit=limit,
            tool_group_id=tool_group_id,
            is_active=is_active,
            instance_type=instance_type,
        )

    # ─── Instance resolution ────────────────────────────────────────────

    async def resolve_instance(
        self,
        tool_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ToolInstance]:
        """
        Resolve a ToolInstance for a given tool slug.
        
        Resolution order:
        1. Direct match by instance slug == tool_slug
        2. Find Tool by slug → get its tool_group_id → first active instance in that group
        
        Returns None if no instance found.
        """
        # 1. Direct slug match
        instance = await self.repo.get_by_slug(tool_slug)
        if instance and instance.is_active:
            return instance
        
        # 2. Resolve via Tool → ToolGroup → instances
        try:
            from sqlalchemy import select
            from app.models.tool import Tool
            
            stmt = select(Tool).where(Tool.slug == tool_slug)
            result = await self.session.execute(stmt)
            tool = result.scalar_one_or_none()
            
            if tool and tool.tool_group_id:
                instances = await self.repo.get_by_tool_group(
                    tool.tool_group_id, is_active=True
                )
                if instances:
                    return instances[0]
        except Exception as e:
            logger.warning(f"Failed to resolve instance for tool '{tool_slug}': {e}")
        
        return None

    # ─── Local instance management (internal) ─────────────────────────

    async def create_local_instance(
        self,
        tool_group_id: UUID,
        slug: str,
        name: str,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ToolInstance:
        """Create a LOCAL instance (internal use only, not exposed via API)."""
        instance = ToolInstance(
            tool_group_id=tool_group_id,
            slug=slug,
            name=name,
            description=description,
            url="",
            config=config,
            instance_type=InstanceType.LOCAL.value,
            health_status="healthy",
            is_active=True,
        )
        result = await self.repo.create(instance)
        logger.info(f"Created local instance: {slug} (group: {tool_group_id})")
        return result

    async def delete_local_instance(self, instance_id: UUID) -> None:
        """Delete a LOCAL instance (internal use only)."""
        instance = await self.get_instance(instance_id)
        await self.repo.delete(instance)
        logger.info(f"Deleted local instance: {instance.slug}")

    # ─── Health check ─────────────────────────────────────────────────

    async def check_health(self, instance_id: UUID) -> HealthCheckResult:
        """Perform health check on a tool instance."""
        instance = await self.get_instance(instance_id)

        # Local instances are always healthy
        if instance.instance_type == InstanceType.LOCAL.value:
            instance.health_status = "healthy"
            await self.repo.update(instance)
            return HealthCheckResult(status="healthy", message="Local instance")

        try:
            result = await self._perform_health_check(instance)
            instance.health_status = result.status
            await self.repo.update(instance)
            return result
        except Exception as e:
            logger.error(f"Health check failed for instance {instance_id}: {e}")
            instance.health_status = "unhealthy"
            await self.repo.update(instance)
            return HealthCheckResult(status="unhealthy", message=str(e))

    async def _perform_health_check(self, instance: ToolInstance) -> HealthCheckResult:
        """Perform actual health check using instance url."""
        url = instance.url
        if not url:
            return HealthCheckResult(
                status="unknown",
                message="No URL configured",
            )

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, follow_redirects=True)

                if response.status_code < 500:
                    return HealthCheckResult(
                        status="healthy",
                        message=f"Connection successful (status: {response.status_code})",
                        details={"status_code": response.status_code},
                    )
                else:
                    return HealthCheckResult(
                        status="unhealthy",
                        message=f"Server error (status: {response.status_code})",
                        details={"status_code": response.status_code},
                    )
        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection failed: {str(e)}",
            )

    # ─── Rescan ───────────────────────────────────────────────────────

    async def rescan_local_instances(self) -> RescanResult:
        """
        Rescan and sync local instances with actual data.
        
        - Ensures RAG global instance exists
        - Syncs collection instances with existing collections
        - Removes orphaned local instances
        """
        from sqlalchemy import select
        from app.models.tool_group import ToolGroup
        from app.models.collection import Collection

        result = RescanResult()

        try:
            # 1. Ensure RAG global instance
            rag_group_stmt = select(ToolGroup).where(ToolGroup.slug == "rag")
            rag_group_result = await self.session.execute(rag_group_stmt)
            rag_group = rag_group_result.scalar_one_or_none()

            if rag_group:
                rag_instance = await self.repo.get_by_slug_and_group(
                    "rag-global", rag_group.id
                )
                if not rag_instance:
                    await self.create_local_instance(
                        tool_group_id=rag_group.id,
                        slug="rag-global",
                        name="RAG Knowledge Base",
                        description="Global RAG knowledge base for document search",
                        config={"scope": "global"},
                    )
                    result.created += 1
                    logger.info("Created RAG global instance")

            # 2. Sync collection instances
            coll_group_stmt = select(ToolGroup).where(ToolGroup.slug == "collection")
            coll_group_result = await self.session.execute(coll_group_stmt)
            coll_group = coll_group_result.scalar_one_or_none()

            if coll_group:
                # Get all active collections
                collections_stmt = select(Collection).where(Collection.is_active == True)  # noqa: E712
                collections_result = await self.session.execute(collections_stmt)
                collections = list(collections_result.scalars().all())

                # Get all local instances in collection group
                existing_instances, _ = await self.repo.list_instances(
                    tool_group_id=coll_group.id,
                    instance_type=InstanceType.LOCAL.value,
                    limit=10000,
                )
                existing_slugs = {i.slug for i in existing_instances}
                expected_slugs = {f"collection-{c.slug}" for c in collections}

                # Create missing instances
                for coll in collections:
                    expected_slug = f"collection-{coll.slug}"
                    if expected_slug not in existing_slugs:
                        instance = await self.create_local_instance(
                            tool_group_id=coll_group.id,
                            slug=expected_slug,
                            name=f"Collection: {coll.name}",
                            description=coll.description or f"Data collection: {coll.name}",
                            config={
                                "collection_id": str(coll.id),
                                "collection_slug": coll.slug,
                                "tenant_id": str(coll.tenant_id),
                                "table_name": coll.table_name,
                            },
                        )
                        # Link collection to instance
                        if not coll.tool_instance_id:
                            coll.tool_instance_id = instance.id
                            await self.session.flush()
                        result.created += 1

                # Remove orphaned instances
                for inst in existing_instances:
                    if inst.slug not in expected_slugs:
                        await self.repo.delete(inst)
                        result.deleted += 1
                        logger.info(f"Removed orphaned collection instance: {inst.slug}")

        except Exception as e:
            logger.error(f"Rescan failed: {e}")
            result.errors += 1

        logger.info(
            f"Rescan complete: created={result.created}, "
            f"updated={result.updated}, deleted={result.deleted}, "
            f"errors={result.errors}"
        )
        return result
