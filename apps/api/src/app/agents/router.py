"""
AgentRouter - pre-runtime маршрутизатор для агентов

Задачи Router:
1. Классифицировать запрос (intent detection)
2. Выбрать агента
3. Проверить prerequisites (required tools/collections)
4. Резолвить effective permissions
5. Выбрать default ToolInstances
6. Определить режим выполнения (full/partial/unavailable)
7. Создать ExecutionRequest
8. Логировать routing decision

Router НЕ делает:
- Не планирует шаги
- Не строит запросы к tools
- Не вызывает LLM для генерации
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.routing_log import RoutingLog
from app.models.tool_instance import ToolInstance
from app.services.agent_service import AgentService
from app.services.permission_service import PermissionService, EffectivePermissions
from app.services.tool_instance_service import ToolInstanceService
from app.services.credential_service import CredentialService
from app.repositories.routing_log_repository import RoutingLogRepository

logger = get_logger(__name__)


class ExecutionMode(str, Enum):
    """Режим выполнения агента"""
    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RoutingStatus(str, Enum):
    """Статус routing decision"""
    SUCCESS = "success"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass
class ToolCapability:
    """Информация о доступном инструменте"""
    tool_slug: str
    instance_id: Optional[UUID] = None
    instance_slug: Optional[str] = None
    has_credentials: bool = False
    required: bool = False
    recommended: bool = False


@dataclass
class MissingRequirements:
    """Информация о недостающих requirements"""
    tools: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)
    
    @property
    def has_missing(self) -> bool:
        return bool(self.tools or self.collections or self.credentials)
    
    def to_message(self) -> str:
        parts = []
        if self.tools:
            parts.append(f"Missing tools: {', '.join(self.tools)}")
        if self.collections:
            parts.append(f"Missing collections: {', '.join(self.collections)}")
        if self.credentials:
            parts.append(f"Missing credentials for: {', '.join(self.credentials)}")
        return "; ".join(parts)


@dataclass
class ExecutionRequest:
    """Запрос на выполнение агента"""
    run_id: UUID
    agent_slug: str
    agent: Agent
    user_id: UUID
    tenant_id: UUID
    
    intent: Optional[str] = None
    intent_confidence: float = 0.0
    
    available_tools: List[ToolCapability] = field(default_factory=list)
    available_collections: List[str] = field(default_factory=list)
    
    tool_instances_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    effective_permissions: Optional[EffectivePermissions] = None
    
    mode: ExecutionMode = ExecutionMode.FULL
    
    missing_requirements: Optional[MissingRequirements] = None
    partial_mode_warning: Optional[str] = None
    
    routing_reasons: List[str] = field(default_factory=list)
    routed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    routing_duration_ms: int = 0


class AgentRouterError(Exception):
    """Base exception for router errors"""
    pass


class AgentUnavailableError(AgentRouterError):
    """Agent cannot be executed due to missing requirements"""
    def __init__(self, message: str, missing: MissingRequirements):
        super().__init__(message)
        self.missing = missing


class AgentRouter:
    """
    Pre-runtime маршрутизатор для агентов.
    
    Пример использования:
        router = AgentRouter(session)
        
        try:
            exec_request = await router.route(
                agent_slug="chat-rag",
                user_id=user_id,
                tenant_id=tenant_id,
                request_text="Найди документацию по API",
            )
            
            # Передаем в AgentRuntime
            await runtime.run(exec_request)
            
        except AgentUnavailableError as e:
            # Агент недоступен - показываем что не хватает
            print(f"Cannot run agent: {e.missing.to_message()}")
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.agent_service = AgentService(session)
        self.permission_service = PermissionService(session)
        self.instance_service = ToolInstanceService(session)
        self.credential_service = CredentialService(session)
        self.routing_log_repo = RoutingLogRepository(session)
    
    async def route(
        self,
        agent_slug: str,
        user_id: UUID,
        tenant_id: UUID,
        request_text: Optional[str] = None,
        allow_partial: bool = False,
    ) -> ExecutionRequest:
        """
        Route request to agent and prepare execution context.
        
        Args:
            agent_slug: Slug of the agent to use
            user_id: User ID
            tenant_id: Tenant ID
            request_text: Original request text (for logging)
            allow_partial: Allow partial execution if some tools unavailable
            
        Returns:
            ExecutionRequest ready for AgentRuntime
            
        Raises:
            AgentUnavailableError: If required tools/collections are missing
        """
        start_time = time.time()
        run_id = uuid.uuid4()
        
        routing_reasons = []
        
        try:
            agent = await self.agent_service.get_agent(agent_slug)
            routing_reasons.append(f"Agent '{agent_slug}' loaded")
            
            effective_perms = await self.permission_service.resolve_permissions(
                user_id=user_id,
                tenant_id=tenant_id,
            )
            routing_reasons.append(
                f"Permissions resolved: {len(effective_perms.allowed_tools)} tools, "
                f"{len(effective_perms.allowed_collections)} collections"
            )
            
            available_tools, tool_instances_map, missing = await self._resolve_tools(
                agent=agent,
                user_id=user_id,
                tenant_id=tenant_id,
                effective_perms=effective_perms,
            )
            
            available_collections = await self._resolve_collections(
                agent=agent,
                effective_perms=effective_perms,
                missing=missing,
            )
            
            mode = self._determine_execution_mode(
                agent=agent,
                missing=missing,
                allow_partial=allow_partial,
            )
            
            if mode == ExecutionMode.UNAVAILABLE:
                routing_reasons.append(f"Execution unavailable: {missing.to_message()}")
                
                await self._log_routing_decision(
                    run_id=run_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    request_text=request_text,
                    agent_slug=agent_slug,
                    mode=mode,
                    missing=missing,
                    available_tools=available_tools,
                    available_collections=available_collections,
                    tool_instances_map=tool_instances_map,
                    routing_reasons=routing_reasons,
                    status=RoutingStatus.UNAVAILABLE,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                
                raise AgentUnavailableError(
                    f"Agent '{agent_slug}' cannot be executed: {missing.to_message()}",
                    missing=missing,
                )
            
            routing_reasons.append(f"Execution mode: {mode.value}")
            
            # Generate partial mode warning if needed
            partial_warning = None
            if mode == ExecutionMode.PARTIAL and missing.has_missing:
                warning_parts = []
                if missing.tools:
                    warning_parts.append(f"tools: {', '.join(missing.tools)}")
                if missing.collections:
                    warning_parts.append(f"collections: {', '.join(missing.collections)}")
                if missing.credentials:
                    warning_parts.append(f"credentials for: {', '.join(missing.credentials)}")
                
                partial_warning = (
                    "⚠️ Running in partial mode. Some capabilities are unavailable:\n"
                    f"{'; '.join(warning_parts)}.\n"
                    "Responses may be incomplete or less accurate."
                )
                routing_reasons.append(f"Partial mode warning: {partial_warning}")
            
            exec_request = ExecutionRequest(
                run_id=run_id,
                agent_slug=agent_slug,
                agent=agent,
                user_id=user_id,
                tenant_id=tenant_id,
                available_tools=available_tools,
                available_collections=available_collections,
                tool_instances_map=tool_instances_map,
                effective_permissions=effective_perms,
                mode=mode,
                missing_requirements=missing if missing.has_missing else None,
                partial_mode_warning=partial_warning,
                routing_reasons=routing_reasons,
                routing_duration_ms=int((time.time() - start_time) * 1000),
            )
            
            await self._log_routing_decision(
                run_id=run_id,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text,
                agent_slug=agent_slug,
                mode=mode,
                missing=missing,
                available_tools=available_tools,
                available_collections=available_collections,
                tool_instances_map=tool_instances_map,
                routing_reasons=routing_reasons,
                status=RoutingStatus.SUCCESS,
                duration_ms=exec_request.routing_duration_ms,
            )
            
            return exec_request
            
        except AgentUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Routing failed: {e}", exc_info=True)
            
            await self._log_routing_decision(
                run_id=run_id,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text,
                agent_slug=agent_slug,
                mode=ExecutionMode.UNAVAILABLE,
                missing=MissingRequirements(),
                available_tools=[],
                available_collections=[],
                tool_instances_map={},
                routing_reasons=routing_reasons + [f"Error: {str(e)}"],
                status=RoutingStatus.FAILED,
                duration_ms=int((time.time() - start_time) * 1000),
                error_message=str(e),
            )
            
            raise AgentRouterError(f"Routing failed: {e}") from e
    
    async def _resolve_tools(
        self,
        agent: Agent,
        user_id: UUID,
        tenant_id: UUID,
        effective_perms: EffectivePermissions,
    ) -> Tuple[List[ToolCapability], Dict[str, Dict[str, Any]], MissingRequirements]:
        """Resolve available tools with instances and credentials"""
        available_tools = []
        tool_instances_map = {}
        missing = MissingRequirements()
        
        all_tool_slugs = agent.get_all_tool_slugs()
        tools_config = {tc["tool_slug"]: tc for tc in agent.tools_config}
        
        for tool_slug in all_tool_slugs:
            config = tools_config.get(tool_slug, {})
            required = config.get("required", False)
            recommended = config.get("recommended", False)
            
            if not effective_perms.is_tool_allowed(tool_slug):
                if required:
                    missing.tools.append(tool_slug)
                continue
            
            instance = await self.instance_service.resolve_instance(
                tool_slug=tool_slug,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            
            has_credentials = False
            if instance:
                has_credentials = await self.credential_service.has_credentials(
                    tool_instance_id=instance.id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                
                if not has_credentials and required:
                    missing.credentials.append(tool_slug)
                
                tool_instances_map[tool_slug] = {
                    "instance_id": str(instance.id),
                    "instance_slug": instance.slug,
                    "has_credentials": has_credentials,
                }
            elif required:
                missing.tools.append(f"{tool_slug} (no instance)")
            
            capability = ToolCapability(
                tool_slug=tool_slug,
                instance_id=instance.id if instance else None,
                instance_slug=instance.slug if instance else None,
                has_credentials=has_credentials,
                required=required,
                recommended=recommended,
            )
            available_tools.append(capability)
        
        return available_tools, tool_instances_map, missing
    
    async def _resolve_collections(
        self,
        agent: Agent,
        effective_perms: EffectivePermissions,
        missing: MissingRequirements,
    ) -> List[str]:
        """Resolve available collections"""
        available_collections = []
        
        all_collection_slugs = agent.get_all_collection_slugs()
        collections_config = {cc["collection_slug"]: cc for cc in agent.collections_config}
        
        for coll_slug in all_collection_slugs:
            config = collections_config.get(coll_slug, {})
            required = config.get("required", False)
            
            if not effective_perms.is_collection_allowed(coll_slug):
                if required:
                    missing.collections.append(coll_slug)
                continue
            
            available_collections.append(coll_slug)
        
        return available_collections
    
    def _determine_execution_mode(
        self,
        agent: Agent,
        missing: MissingRequirements,
        allow_partial: bool,
    ) -> ExecutionMode:
        """Determine execution mode based on missing requirements"""
        if not missing.has_missing:
            return ExecutionMode.FULL
        
        if allow_partial and agent.supports_partial_mode:
            return ExecutionMode.PARTIAL
        
        return ExecutionMode.UNAVAILABLE
    
    async def _log_routing_decision(
        self,
        run_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        request_text: Optional[str],
        agent_slug: str,
        mode: ExecutionMode,
        missing: MissingRequirements,
        available_tools: List[ToolCapability],
        available_collections: List[str],
        tool_instances_map: Dict[str, Dict[str, Any]],
        routing_reasons: List[str],
        status: RoutingStatus,
        duration_ms: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Log routing decision for observability"""
        try:
            log = RoutingLog(
                run_id=run_id,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text[:1000] if request_text else None,
                selected_agent_slug=agent_slug,
                routing_reasons=routing_reasons,
                missing_tools=missing.tools,
                missing_collections=missing.collections,
                missing_credentials=missing.credentials,
                execution_mode=mode.value,
                effective_tools=[t.tool_slug for t in available_tools],
                effective_collections=available_collections,
                tool_instances_map=tool_instances_map,
                routing_duration_ms=duration_ms,
                status=status.value,
                error_message=error_message,
            )
            
            await self.routing_log_repo.create(log)
            
        except Exception as e:
            logger.error(f"Failed to log routing decision: {e}")
