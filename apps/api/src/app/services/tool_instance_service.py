"""
ToolInstanceService - управление инстансами инструментов
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool import Tool
from app.models.tool_instance import ToolInstance, InstanceScope, HealthStatus
from app.repositories.tool_instance_repository import ToolInstanceRepository
from app.repositories.tool_repository import ToolRepository

logger = get_logger(__name__)


class ToolInstanceError(Exception):
    """Base exception for tool instance operations"""
    pass


class ToolInstanceNotFoundError(ToolInstanceError):
    """Tool instance not found"""
    pass


class ToolNotFoundError(ToolInstanceError):
    """Tool not found"""
    pass


@dataclass
class HealthCheckResult:
    """Result of health check"""
    status: HealthStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ToolInstanceService:
    """
    Сервис для управления ToolInstance.
    
    Отвечает за:
    - CRUD операции с инстансами
    - Резолв инстанса по приоритету (User > Tenant > Default)
    - Health check инстансов
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ToolInstanceRepository(session)
        self.tool_repo = ToolRepository(session)
    
    async def create_instance(
        self,
        tool_slug: str,
        slug: str,
        name: str,
        scope: str,
        connection_config: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        description: Optional[str] = None,
        is_default: bool = False,
    ) -> ToolInstance:
        """Create a new tool instance"""
        tool = await self.tool_repo.get_by_slug(tool_slug)
        if not tool:
            raise ToolNotFoundError(f"Tool '{tool_slug}' not found")
        
        existing = await self.repo.get_by_slug(slug)
        if existing:
            raise ToolInstanceError(f"Instance with slug '{slug}' already exists")
        
        self._validate_scope(scope, tenant_id, user_id)
        
        instance = ToolInstance(
            tool_id=tool.id,
            slug=slug,
            name=name,
            description=description,
            scope=scope,
            tenant_id=tenant_id,
            user_id=user_id,
            connection_config=connection_config,
            is_default=is_default,
            is_active=True,
            health_status=HealthStatus.UNKNOWN.value,
        )
        
        return await self.repo.create(instance)
    
    async def get_instance(self, instance_id: UUID) -> ToolInstance:
        """Get instance by ID"""
        instance = await self.repo.get_by_id(instance_id)
        if not instance:
            raise ToolInstanceNotFoundError(f"Instance '{instance_id}' not found")
        return instance
    
    async def get_instance_by_slug(self, slug: str) -> ToolInstance:
        """Get instance by slug"""
        instance = await self.repo.get_by_slug(slug)
        if not instance:
            raise ToolInstanceNotFoundError(f"Instance '{slug}' not found")
        return instance
    
    async def update_instance(
        self,
        instance_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        connection_config: Optional[Dict[str, Any]] = None,
        is_default: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> ToolInstance:
        """Update tool instance"""
        instance = await self.get_instance(instance_id)
        
        if name is not None:
            instance.name = name
        if description is not None:
            instance.description = description
        if connection_config is not None:
            instance.connection_config = connection_config
        if is_default is not None:
            instance.is_default = is_default
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
        tool_id: Optional[UUID] = None,
        tool_slug: Optional[str] = None,
        scope: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[ToolInstance], int]:
        """List tool instances with filters"""
        if tool_slug and not tool_id:
            tool = await self.tool_repo.get_by_slug(tool_slug)
            if tool:
                tool_id = tool.id
        
        return await self.repo.list_instances(
            skip=skip,
            limit=limit,
            tool_id=tool_id,
            scope=scope,
            tenant_id=tenant_id,
            is_active=is_active,
        )
    
    async def resolve_instance(
        self,
        tool_slug: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[ToolInstance]:
        """
        Resolve the best instance for a tool following priority:
        User (is_default) > Tenant (is_default) > Default (is_default) >
        User (any) > Tenant (any) > Default (any)
        """
        return await self.repo.get_by_tool_slug(tool_slug, user_id, tenant_id)
    
    async def check_health(self, instance_id: UUID) -> HealthCheckResult:
        """
        Perform health check on a tool instance.
        
        This is a basic implementation that checks if connection_config is valid.
        Specific tools should override this with actual connectivity checks.
        """
        instance = await self.get_instance(instance_id)
        
        try:
            result = await self._perform_health_check(instance)
            
            await self.repo.update_health_status(
                instance_id=instance_id,
                status=result.status.value,
                error=result.message if result.status == HealthStatus.UNHEALTHY else None,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Health check failed for instance {instance_id}: {e}")
            
            await self.repo.update_health_status(
                instance_id=instance_id,
                status=HealthStatus.UNHEALTHY.value,
                error=str(e),
            )
            
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    async def _perform_health_check(self, instance: ToolInstance) -> HealthCheckResult:
        """
        Perform actual health check.
        
        This is a basic implementation. For real health checks,
        we need to know the tool type and make appropriate requests.
        """
        config = instance.connection_config or {}
        
        if not config:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="No connection config provided",
            )
        
        url = config.get("url") or config.get("base_url")
        if url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, follow_redirects=True)
                    
                    if response.status_code < 500:
                        return HealthCheckResult(
                            status=HealthStatus.HEALTHY,
                            message=f"Connection successful (status: {response.status_code})",
                            details={"status_code": response.status_code},
                        )
                    else:
                        return HealthCheckResult(
                            status=HealthStatus.UNHEALTHY,
                            message=f"Server error (status: {response.status_code})",
                            details={"status_code": response.status_code},
                        )
            except Exception as e:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message=f"Connection failed: {str(e)}",
                )
        
        return HealthCheckResult(
            status=HealthStatus.UNKNOWN,
            message="Cannot determine health - no URL in config",
        )
    
    def _validate_scope(
        self,
        scope: str,
        tenant_id: Optional[UUID],
        user_id: Optional[UUID],
    ) -> None:
        """Validate scope and required IDs"""
        if scope == InstanceScope.DEFAULT.value:
            if tenant_id or user_id:
                raise ToolInstanceError("Default scope cannot have tenant_id or user_id")
        elif scope == InstanceScope.TENANT.value:
            if not tenant_id:
                raise ToolInstanceError("Tenant scope requires tenant_id")
            if user_id:
                raise ToolInstanceError("Tenant scope cannot have user_id")
        elif scope == InstanceScope.USER.value:
            if not tenant_id or not user_id:
                raise ToolInstanceError("User scope requires both tenant_id and user_id")
        else:
            raise ToolInstanceError(f"Invalid scope: {scope}")
