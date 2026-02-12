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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.agent_binding import AgentBinding
from app.models.tool import Tool
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
    
    # v2: prompt from AgentVersion
    prompt: str = ""
    
    # v2: resolved policy/limit data from AgentVersion → PolicyVersion/LimitVersion
    policy_data: Dict[str, Any] = field(default_factory=dict)
    limit_data: Dict[str, Any] = field(default_factory=dict)
    
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
            agent = await self.agent_service.get_agent_by_slug(agent_slug)
            routing_reasons.append(f"Agent '{agent_slug}' loaded")
            
            # v2: resolve active version for prompt, policy, limits
            agent_version = await self.agent_service.resolve_active_version(agent_slug)
            
            # Resolve policy_data and limit_data from version references
            policy_data: Dict[str, Any] = {}
            limit_data: Dict[str, Any] = {}
            
            if agent_version and agent_version.policy_id:
                policy_data = await self._resolve_policy_data(agent_version.policy_id)
                routing_reasons.append(f"Policy resolved: {agent_version.policy_id}")
            
            if agent_version and agent_version.limit_id:
                limit_data = await self._resolve_limit_data(agent_version.limit_id)
                routing_reasons.append(f"Limit resolved: {agent_version.limit_id}")
            
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
                prompt=agent_version.prompt,
                policy_data=policy_data,
                limit_data=limit_data,
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
    
    async def _get_agent_bindings(
        self,
        agent: Agent,
    ) -> List[Dict[str, Any]]:
        """Load agent bindings with tool slugs from DB (v2: via current_version_id)"""
        from app.models.agent_version import AgentVersion
        
        if not agent.current_version_id:
            return []
        
        stmt = (
            select(
                AgentBinding.tool_id,
                AgentBinding.tool_instance_id,
                AgentBinding.credential_strategy,
                Tool.slug.label("tool_slug"),
            )
            .join(Tool, AgentBinding.tool_id == Tool.id)
            .where(AgentBinding.agent_version_id == agent.current_version_id)
        )
        result = await self.session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def _resolve_tools(
        self,
        agent: Agent,
        user_id: UUID,
        tenant_id: UUID,
        effective_perms: EffectivePermissions,
    ) -> Tuple[List[ToolCapability], Dict[str, Dict[str, Any]], MissingRequirements]:
        """Resolve available tools with instances and credentials via AgentBinding"""
        available_tools = []
        tool_instances_map = {}
        missing = MissingRequirements()
        
        bindings = await self._get_agent_bindings(agent)
        
        for binding in bindings:
            tool_slug = binding["tool_slug"]
            
            if not effective_perms.is_tool_allowed(tool_slug):
                missing.tools.append(tool_slug)
                continue
            
            # Use binding's explicit tool_instance_id if set, otherwise resolve
            binding_instance_id = binding.get("tool_instance_id")
            instance = None
            if binding_instance_id:
                try:
                    instance = await self.instance_service.get_instance(binding_instance_id)
                except Exception:
                    instance = None
            if not instance:
                instance = await self.instance_service.resolve_instance(
                    tool_slug=tool_slug,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
            
            has_credentials = False
            if instance:
                # Local instances don't require credentials
                if instance.instance_type == "local":
                    has_credentials = True
                else:
                    has_credentials = await self.credential_service.has_credentials(
                        tool_instance_id=instance.id,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                
                if not has_credentials:
                    missing.credentials.append(tool_slug)
                
                tool_instances_map[tool_slug] = {
                    "instance_id": str(instance.id),
                    "instance_slug": instance.slug,
                    "has_credentials": has_credentials,
                }
            else:
                missing.tools.append(f"{tool_slug} (no instance)")
            
            capability = ToolCapability(
                tool_slug=tool_slug,
                instance_id=instance.id if instance else None,
                instance_slug=instance.slug if instance else None,
                has_credentials=has_credentials,
                required=True,
                recommended=False,
            )
            available_tools.append(capability)
        
        return available_tools, tool_instances_map, missing
    
    async def _resolve_policy_data(self, policy_id: UUID) -> Dict[str, Any]:
        """Load policy_json from the active PolicyVersion via Policy.current_version_id"""
        from app.models.policy import Policy, PolicyVersion
        
        try:
            result = await self.session.execute(
                select(Policy).where(Policy.id == policy_id)
            )
            policy = result.scalar_one_or_none()
            if not policy or not policy.current_version_id:
                return {}
            
            ver_result = await self.session.execute(
                select(PolicyVersion).where(PolicyVersion.id == policy.current_version_id)
            )
            version = ver_result.scalar_one_or_none()
            if version and version.policy_json:
                return version.policy_json
            return {}
        except Exception as e:
            logger.warning(f"Failed to resolve policy data for {policy_id}: {e}")
            return {}

    async def _resolve_limit_data(self, limit_id: UUID) -> Dict[str, Any]:
        """Load limit fields from the active LimitVersion via Limit.current_version_id"""
        from app.models.limit import Limit, LimitVersion
        
        try:
            result = await self.session.execute(
                select(Limit).where(Limit.id == limit_id)
            )
            limit = result.scalar_one_or_none()
            if not limit or not limit.current_version_id:
                return {}
            
            ver_result = await self.session.execute(
                select(LimitVersion).where(LimitVersion.id == limit.current_version_id)
            )
            version = ver_result.scalar_one_or_none()
            if not version:
                return {}
            
            data: Dict[str, Any] = {}
            if version.max_steps is not None:
                data["max_steps"] = version.max_steps
            if version.max_tool_calls is not None:
                data["max_tool_calls"] = version.max_tool_calls
            if version.max_wall_time_ms is not None:
                data["max_wall_time_ms"] = version.max_wall_time_ms
            if version.tool_timeout_ms is not None:
                data["tool_timeout_ms"] = version.tool_timeout_ms
            if version.max_retries is not None:
                data["max_retries"] = version.max_retries
            if version.extra_config:
                data.update(version.extra_config)
            return data
        except Exception as e:
            logger.warning(f"Failed to resolve limit data for {limit_id}: {e}")
            return {}

    async def _resolve_collections(
        self,
        agent: Agent,
        effective_perms: EffectivePermissions,
        missing: MissingRequirements,
    ) -> List[str]:
        """Resolve available collections (currently empty — collections are resolved via tools)"""
        return []
    
    def _determine_execution_mode(
        self,
        agent: Agent,
        missing: MissingRequirements,
        allow_partial: bool,
    ) -> ExecutionMode:
        """Determine execution mode based on missing requirements"""
        if not missing.has_missing:
            return ExecutionMode.FULL
        
        if allow_partial:
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
