"""
ExecutionPreflight — фасад для подготовки ExecutionRequest.

Координирует:
- AgentResolver (загрузка агента + версии + available_actions)
- OperationRouter (permissions + data instances + operations + execution targets)
- Определение execution mode (FULL / PARTIAL / UNAVAILABLE)
- Сборку ExecutionRequest
- Логирование routing decision

НЕ делает:
- Не выбирает агента (agent_slug уже определён triage/pipeline)
- Не планирует шаги
- Не вызывает LLM
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_resolver import AgentResolver
from app.agents.contracts import (
    AvailableActions,
    MissingRequirements,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.operation_router import OperationRouter
from app.agents.preflight_policy import apply_operation_policy_filter
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.runtime_graph import RuntimeExecutionGraph
from app.agents.runtime_trace_logger import RuntimeTraceLogger
from app.core.exceptions import AgentUnavailableError, AppError as PreflightError
from app.core.logging import get_logger
from app.models.agent import Agent
from app.services.permission_service import EffectivePermissions, PermissionService

logger = get_logger(__name__)


class ExecutionMode(str, Enum):
    """Режим выполнения агента."""
    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RoutingStatus(str, Enum):
    """Статус routing decision."""
    SUCCESS = "success"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass
class ExecutionRequest:
    """Запрос на выполнение агента."""
    run_id: UUID
    agent_slug: str
    agent: Agent
    user_id: UUID
    tenant_id: UUID

    # v2: prompt from AgentVersion
    prompt: str = ""
    agent_version: Optional["AgentVersion"] = None

    # v2: resolved policy/limit data from AgentVersion → PolicyVersion/LimitVersion
    policy_data: Dict[str, Any] = field(default_factory=dict)
    limit_data: Dict[str, Any] = field(default_factory=dict)

    intent: Optional[str] = None
    intent_confidence: float = 0.0

    available_actions: Optional[AvailableActions] = None
    resolved_data_instances: List[ResolvedDataInstance] = field(default_factory=list)
    resolved_operations: List[ResolvedOperation] = field(default_factory=list)
    execution_graph: RuntimeExecutionGraph = field(default_factory=RuntimeExecutionGraph)

    effective_permissions: Optional[EffectivePermissions] = None

    mode: ExecutionMode = ExecutionMode.FULL

    missing_requirements: Optional[MissingRequirements] = None
    partial_mode_warning: Optional[str] = None

    routing_reasons: List[str] = field(default_factory=list)
    routed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    routing_duration_ms: int = 0
    request_text: Optional[str] = None
    sandbox_session_id: Optional[UUID] = None
    sandbox_branch_id: Optional[UUID] = None
    sandbox_snapshot_id: Optional[UUID] = None
    sandbox_trace: Dict[str, Any] = field(default_factory=dict)


class ExecutionPreflight:
    """Фасад: собирает ExecutionRequest из AgentResolver + OperationRouter.

    Пример использования:
        preflight = ExecutionPreflight(session)
        exec_request = await preflight.prepare(
            agent_slug="chat-rag",
            user_id=user_id,
            tenant_id=tenant_id,
            request_text="Найди документацию по API",
        )
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.agent_resolver = AgentResolver(session)
        self.operation_router = OperationRouter(session)
        self.runtime_rbac_resolver = RuntimeRbacResolver(PermissionService(session))
        self.trace_logger = RuntimeTraceLogger(session=session)

    async def prepare(
        self,
        agent_slug: str,
        user_id: UUID,
        tenant_id: UUID,
        request_text: Optional[str] = None,
        allow_partial: bool = False,
        agent_version_id: Optional[UUID] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        include_routable_agents: bool = True,
        routable_agents_override: Optional[List[Any]] = None,
        effective_permissions_override: Optional[EffectivePermissions] = None,
    ) -> ExecutionRequest:
        """Prepare ExecutionRequest for an already selected agent.

        Args:
            agent_slug: Slug агента (уже выбран triage/pipeline).
            user_id: User UUID.
            tenant_id: Tenant UUID.
            request_text: Текст запроса (для логирования).
            allow_partial: Разрешить partial execution.
            agent_version_id: Override версии (sandbox).

        Returns:
            ExecutionRequest, готовый к передаче в runtime.

        Raises:
            AgentUnavailableError: Если required operations/collections недоступны.
            PreflightError: Если preflight не удался.
        """
        start_time = time.time()
        run_id = uuid.uuid4()
        routing_reasons: List[str] = []

        try:
            # 1. Resolve agent + version
            agent_result = await self.agent_resolver.resolve(
                agent_slug=agent_slug,
                tenant_id=tenant_id,
                agent_version_id=agent_version_id,
                include_routable_agents=include_routable_agents,
            )
            routing_reasons.append(f"Agent '{agent_slug}' loaded")

            # 2. Resolve instances + operations + permissions
            default_tool_allow = bool((platform_config or {}).get("default_tool_allow", True))
            default_collection_allow = bool(
                (platform_config or {}).get("default_collection_allow", True)
            )
            operation_result = await self.operation_router.resolve(
                user_id=user_id,
                tenant_id=tenant_id,
                effective_permissions=effective_permissions_override,
                default_tool_allow=default_tool_allow,
                default_collection_allow=default_collection_allow,
                sandbox_overrides=sandbox_overrides,
            )
            if not self.runtime_rbac_resolver.is_agent_allowed(
                effective_permissions=operation_result.effective_permissions,
                agent_slug=agent_slug,
                default_allow=True,
            ):
                raise AgentUnavailableError(
                    f"Access denied for agent '{agent_slug}' by RBAC policy",
                    missing=MissingRequirements(),
                    reason_code="rbac_agent_invoke_denied",
                    details={"agent_slug": agent_slug},
                )
            routing_reasons.append(
                f"Permissions resolved: "
                f"{len(operation_result.resolved_operations)} operations, "
                f"{len(operation_result.resolved_data_instances)} data instances"
            )

            # 2b. Apply agent capability filter (allowed_collection_ids on agent container)
            allowed_collection_ids = agent_result.agent.allowed_collection_ids if agent_result.agent else None
            if allowed_collection_ids is not None:
                before_count = len(operation_result.resolved_data_instances)
                allowed_set = {str(collection_id) for collection_id in allowed_collection_ids}
                operation_result.resolved_data_instances = [
                    inst for inst in operation_result.resolved_data_instances
                    if str((inst.collection_id or "")) in allowed_set
                ]
                allowed_op_slugs = set()
                for op in operation_result.resolved_operations:
                    binding = operation_result.execution_graph.get(op.operation_slug)
                    context_config = binding.context.config if binding else {}
                    if str((context_config or {}).get("collection_id") or "") in allowed_set:
                        allowed_op_slugs.add(op.operation_slug)
                operation_result.resolved_operations = [
                    op for op in operation_result.resolved_operations
                    if op.operation_slug in allowed_op_slugs
                ]
                operation_result.execution_graph.filter_by_operation_slugs(allowed_op_slugs)
                after_count = len(operation_result.resolved_data_instances)
                routing_reasons.append(
                    f"Agent capability filter: {before_count} → {after_count} instances "
                    f"(collections whitelist: {sorted(allowed_set)})"
                )

            # 2c. Apply platform operation policy filter before planner snapshot.
            filtered_out = apply_operation_policy_filter(
                operation_result=operation_result,
                platform_config=platform_config or {},
            )
            if filtered_out:
                operation_result.missing.tools.extend(sorted(filtered_out))
                routing_reasons.append(
                    f"Platform policy filtered operations: {', '.join(sorted(filtered_out))}"
                )

            # 3. Build available_actions from resolved operations
            if include_routable_agents:
                if routable_agents_override is not None:
                    routable_agents = list(routable_agents_override)
                    routing_reasons.append(
                        f"Routable agents source: snapshot ({len(routable_agents)})"
                    )
                else:
                    routable_agents = await self.agent_resolver.agent_service.list_routable_agents()
            else:
                routable_agents = []
            if routable_agents:
                routable_agents, denied_agent_slugs = self.runtime_rbac_resolver.filter_agents_by_slug(
                    routable_agents,
                    effective_permissions=operation_result.effective_permissions,
                    slug_getter=lambda item: getattr(item, "slug", None),
                    default_allow=True,
                )
                if denied_agent_slugs:
                    routing_reasons.append(
                        "RBAC filtered routable agents: "
                        + ", ".join(sorted(denied_agent_slugs))
                    )
            agent_result_with_actions = await self.agent_resolver.available_actions_builder.build(
                agent=agent_result.agent,
                agent_version=agent_result.agent_version,
                resolved_operations=operation_result.resolved_operations,
                routable_agents=routable_agents,
            )

            # 4. Determine execution mode
            mode = self._determine_execution_mode(
                missing=operation_result.missing,
                available_operations_count=len(operation_result.resolved_operations),
                allow_partial=allow_partial,
            )

            if mode == ExecutionMode.UNAVAILABLE:
                routing_reasons.append(f"Execution unavailable: {operation_result.missing.to_message()}")
                await self._log_decision(
                    run_id=run_id, user_id=user_id, tenant_id=tenant_id,
                    request_text=request_text, agent_slug=agent_slug,
                    mode=mode, missing=operation_result.missing,
                    available_operations=operation_result.resolved_operations,
                    available_collections=[item.slug for item in operation_result.resolved_data_instances],
                    execution_graph=operation_result.execution_graph,
                    routing_reasons=routing_reasons,
                    status=RoutingStatus.UNAVAILABLE,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                raise AgentUnavailableError(
                    f"Agent '{agent_slug}' cannot be executed: {operation_result.missing.to_message()}",
                    missing=operation_result.missing,
                )

            routing_reasons.append(f"Execution mode: {mode.value}")

            # 5. Generate partial mode warning
            partial_warning = self._build_partial_warning(operation_result.missing, mode)
            if partial_warning:
                routing_reasons.append(f"Partial mode warning: {partial_warning}")

            # 6. Build ExecutionRequest
            exec_request = ExecutionRequest(
                run_id=run_id,
                agent_slug=agent_slug,
                agent=agent_result.agent,
                agent_version=agent_result.agent_version,
                user_id=user_id,
                tenant_id=tenant_id,
                prompt=agent_result.agent_version.compiled_prompt if agent_result.agent_version else "",
                available_actions=agent_result_with_actions,
                resolved_data_instances=operation_result.resolved_data_instances,
                resolved_operations=operation_result.resolved_operations,
                execution_graph=operation_result.execution_graph,
                effective_permissions=operation_result.effective_permissions,
                mode=mode,
                missing_requirements=operation_result.missing if operation_result.missing.has_missing else None,
                partial_mode_warning=partial_warning,
                routing_reasons=routing_reasons,
                routing_duration_ms=int((time.time() - start_time) * 1000),
                request_text=request_text[:500] if request_text else None,
            )

            await self._log_decision(
                run_id=run_id, user_id=user_id, tenant_id=tenant_id,
                request_text=request_text, agent_slug=agent_slug,
                mode=mode, missing=operation_result.missing,
                available_operations=operation_result.resolved_operations,
                available_collections=[item.slug for item in operation_result.resolved_data_instances],
                execution_graph=operation_result.execution_graph,
                routing_reasons=routing_reasons,
                status=RoutingStatus.SUCCESS,
                duration_ms=exec_request.routing_duration_ms,
            )

            return exec_request

        except AgentUnavailableError:
            raise
        except Exception as e:
            logger.error(f"Preflight failed: {e}", exc_info=True)
            await self._log_decision(
                run_id=run_id, user_id=user_id, tenant_id=tenant_id,
                request_text=request_text, agent_slug=agent_slug,
                mode=ExecutionMode.UNAVAILABLE,
                missing=MissingRequirements(),
                available_operations=[],
                available_collections=[],
                execution_graph=RuntimeExecutionGraph(),
                routing_reasons=routing_reasons + [f"Error: {str(e)}"],
                status=RoutingStatus.FAILED,
                duration_ms=int((time.time() - start_time) * 1000),
                error_message=str(e),
            )
            raise PreflightError(f"Preflight failed: {e}") from e

    @staticmethod
    def _determine_execution_mode(
        missing: MissingRequirements,
        available_operations_count: int,
        allow_partial: bool,
    ) -> ExecutionMode:
        """Determine execution mode based on missing requirements."""
        if not missing.has_missing:
            return ExecutionMode.FULL
        if available_operations_count > 0:
            return ExecutionMode.PARTIAL
        if allow_partial:
            return ExecutionMode.PARTIAL
        return ExecutionMode.UNAVAILABLE

    @staticmethod
    def _build_partial_warning(
        missing: MissingRequirements,
        mode: ExecutionMode,
    ) -> Optional[str]:
        """Generate partial mode warning if applicable."""
        if mode != ExecutionMode.PARTIAL or not missing.has_missing:
            return None
        warning_parts = []
        if missing.tools:
            warning_parts.append(f"tools: {', '.join(missing.tools)}")
        if missing.collections:
            warning_parts.append(f"collections: {', '.join(missing.collections)}")
        if missing.credentials:
            warning_parts.append(f"credentials for: {', '.join(missing.credentials)}")
        return (
            "Running in partial mode. Some capabilities are unavailable:\n"
            f"{'; '.join(warning_parts)}.\n"
            "Responses may be incomplete or less accurate."
        )


    async def _log_decision(
        self,
        run_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        request_text: Optional[str],
        agent_slug: str,
        mode: ExecutionMode,
        missing: MissingRequirements,
        available_operations: List[ResolvedOperation],
        available_collections: List[str],
        execution_graph: RuntimeExecutionGraph,
        routing_reasons: List[str],
        status: RoutingStatus,
        duration_ms: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Log routing decision for observability."""
        try:
            execution_targets, _, _ = execution_graph.to_legacy_maps()
            await self.trace_logger.trace.log_routing_decision(
                run_id=run_id,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text,
                agent_slug=agent_slug,
                mode=mode,
                missing=missing,
                available_operations=available_operations,
                available_collections=available_collections,
                execution_targets=execution_targets,
                routing_reasons=routing_reasons,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
        except Exception as e:
            logger.error(f"Failed to log routing decision: {e}")
