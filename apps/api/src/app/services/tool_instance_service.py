"""
ToolInstanceService v2 - управление инстансами инструментов.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool_instance import ToolInstance
from app.repositories.tool_instance_repository import ToolInstanceRepository

logger = get_logger(__name__)


class ToolInstanceError(Exception):
    pass


class ToolInstanceNotFoundError(ToolInstanceError):
    pass


@dataclass
class HealthCheckResult:
    """Result of health check"""
    status: str  # "healthy" | "unhealthy" | "unknown"
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ToolInstanceService:
    """
    Сервис для управления ToolInstance v2.

    Отвечает за:
    - CRUD операции с инстансами
    - Health check инстансов
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ToolInstanceRepository(session)

    async def create_instance(
        self,
        tool_group_id: UUID,
        name: str,
        url: str,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ToolInstance:
        """Create a new tool instance."""
        instance = ToolInstance(
            tool_group_id=tool_group_id,
            name=name,
            url=url,
            description=description,
            config=config,
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
    ) -> ToolInstance:
        """Update tool instance"""
        instance = await self.get_instance(instance_id)

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

        return await self.repo.update(instance)

    async def delete_instance(self, instance_id: UUID) -> None:
        """Delete tool instance"""
        instance = await self.get_instance(instance_id)
        await self.repo.delete(instance)

    async def list_instances(
        self,
        skip: int = 0,
        limit: int = 100,
        tool_group_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        return await self.repo.list_instances(
            skip=skip,
            limit=limit,
            tool_group_id=tool_group_id,
            is_active=is_active,
        )

    async def check_health(self, instance_id: UUID) -> HealthCheckResult:
        """Perform health check on a tool instance."""
        instance = await self.get_instance(instance_id)

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
