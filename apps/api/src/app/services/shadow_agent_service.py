"""Adapt one authenticated API invocation to the canonical agent executor."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID, uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import RuntimeDependencies, ToolContext
from app.core.db import get_session_factory
from app.core.exceptions import ConflictError, ExternalServiceError, ForbiddenError, ValidationError
from app.core.http.clients import LLMClientProtocol
from app.models.agent import Agent, AgentType
from app.models.agent_version import AgentVersion, AgentVersionStatus
from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.orchestrator_contracts import (
    FreshnessPolicy, ResponseSpec, TaskConfirmationRequired, TaskExecutionError, TaskRequest,
)
from app.runtime.turn_state import RuntimeTurnState
from app.schemas.shadow_agents import ShadowAgentRequest, ShadowAgentResponse
from app.services.agent_service import AgentService
from app.services.memory_scope_preferences_service import MemoryScopePreferencesService
from app.services.shadow_execution_guard_service import ShadowExecutionGuardService
from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError
from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.memory.effective_scope import EffectiveScopeContext
from app.services.permission_service import PermissionService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.runtime_event_logger import (
    RuntimeEventLogger,
    RuntimeEventJournalFactory, RuntimeLogContext, RuntimeLoggingLevel,
)


logger = logging.getLogger(__name__)


class ShadowAgentService:
    def __init__(self, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self.session = session
        self.executor = AgentExecutor(session=session, llm_client=llm_client)

    async def validate(self, request: ShadowAgentRequest, *, user_id: UUID, tenant_id: UUID) -> tuple[Agent, AgentVersion]:
        agents = AgentService(self.session)
        agent = await agents.get_agent_by_slug(request.agent)
        permissions = await PermissionService(self.session).resolve_permissions(
            user_id=user_id, tenant_id=tenant_id,
        )
        if not permissions.is_agent_allowed(agent.slug):
            raise ForbiddenError("Access denied for agent invocation")
        if agent.agent_type != AgentType.SHADOW.value:
            raise ConflictError("This endpoint accepts only shadow agents")
        version = await agents.resolve_published_version(agent.slug, tenant_id=tenant_id)
        if version.status != AgentVersionStatus.PUBLISHED.value:
            raise ConflictError("Shadow invocation requires a published agent version")
        return agent, version

    async def invoke(
        self, request: ShadowAgentRequest, *, user_id: UUID, tenant_id: UUID,
        scopes: list[str], request_id: str,
        invocation_id: UUID | None = None, claim_id: UUID | None = None,
    ) -> ShadowAgentResponse:
        agent, version = await self.validate(request, user_id=user_id, tenant_id=tenant_id)
        scope_context = await self.resolve_scope_context(request, user_id=user_id, tenant_id=tenant_id)
        platform_config = await RuntimeConfigService(self.session).get_pipeline_config()
        run_id, execution_id = uuid4(), uuid4()
        level = RuntimeLoggingLevel.parse(agent.logging_level)
        session_factory = get_session_factory()
        journal = RuntimeEventJournalFactory.create(
            context=RuntimeLogContext(
                run_id=run_id, level=level, origin="shadow", user_id=user_id,
                tenant_id=tenant_id, entity_type="run", entity_id=str(run_id),
                correlation_id=request_id,
            ), session_factory=session_factory,
        )
        ctx = ToolContext(
            user_id=user_id, tenant_id=tenant_id, request_id=request_id, scopes=scopes,
            extra={"shadow_execution": True, "runtime_root_run_id": str(run_id),
                   "runtime_event_logger": journal},
        )
        ctx.extra["memory_search_scope_keys"] = scope_context.keys
        ctx.extra["memory_execution_context"] = memory_execution_context(scope_context.keys)
        guard = ShadowExecutionGuardService(
            session_factory, run_id=run_id, claim_id=claim_id or execution_id, invocation_id=invocation_id,
        )
        ctx.extra["runtime_execution_guard_service"] = guard
        ctx.set_runtime_deps(RuntimeDependencies(session_factory=session_factory))
        task = TaskRequest(
            task_id=str(uuid4()), executor=agent.slug, intent="Shadow invocation",
            instructions=("Perform your configured mission using the supplied task inputs. "
                          "Follow the output format defined in your configured mission exactly. "
                          "Put the mission result in structured_response: JSON data stays JSON; "
                          "a textual result is a JSON string preserving its content and formatting. "
                          "The completion envelope is internal and is not part of the mission result. "
                          "Represent unknown values as JSON null, not the string None. "
                          "If your configured mission defines a fallback for insufficient input, "
                          "return that fallback in structured_response with completion=fulfilled: "
                          "applying the mission's fallback is a completed task. "
                          "Use unfulfillable only when neither the requested result nor a mission-defined fallback can be produced. "
                          "Use the available tools and sources when needed. No chat history is supplied. "
                          "User interactions are unavailable in this API; do not bypass operation confirmation requirements."),
            inputs=request.data, scope_context=scope_context.model_payload(),
            freshness_policy=(FreshnessPolicy.REQUIRE_RETRIEVAL if version.requires_fresh_retrieval
                              else FreshnessPolicy.ALLOW_MEMORY),
            response_spec=ResponseSpec(mode="structured"),
        )
        state = RuntimeTurnState(
            run_id=run_id, user_id=user_id, tenant_id=tenant_id, goal=task.instructions,
        )
        # Release request reads before the potentially long LLM call. Runtime
        # preflight and journal writes use their own short-lived sessions.
        await self.session.commit()
        agent_journal = journal.for_entity(
            entity_type="agent_execution", entity_id=str(execution_id),
            parent_entity_type="run", parent_entity_id=str(run_id), level=level,
        )
        status = "failed"
        await journal.emit(RuntimeEvent.run_start(
            run_id=str(run_id), agent_slug=agent.slug, agent_version_id=str(version.id),
            agent_version=version.version,
        ), phase=OrchestrationPhase.PIPELINE)
        await agent_journal.emit(RuntimeEvent.agent_start(
            agent_execution_id=str(execution_id), parent_entity_type="run",
            parent_entity_id=str(run_id), agent_slug=agent.slug, task_id=task.task_id,
            task_title=version.mission, agent_version_id=str(version.id),
        ), phase=OrchestrationPhase.AGENT)
        try:
            await guard.start()
            receipt = await self.executor.execute_attempt(
                request=task, runtime_state=state, messages=[], ctx=ctx,
                user_id=user_id, tenant_id=tenant_id, platform_config=platform_config,
                agent_version_id=version.id, lifecycle_agent_execution_id=str(execution_id),
                runtime_log_parent={"entity_type": "run", "entity_id": str(run_id)},
            )
            declaration = receipt.declaration
            if declaration.completion_claim != "fulfilled" or declaration.needs:
                raise ExternalServiceError("Shadow agent did not fulfill the task")
            try:
                response = ShadowAgentResponse(agent=agent.slug, result=declaration.structured_response)
                # Python's JSON parser accepts NaN/Infinity; the public contract does not.
                json.dumps(response.model_dump(), allow_nan=False)
            except (PydanticValidationError, ValueError, TypeError) as exc:
                raise ExternalServiceError("Shadow agent returned an invalid JSON value") from exc
            await self._safe_emit(agent_journal, RuntimeEvent.status(
                "shadow_result_validated", agent_slug=agent.slug,
                agent_version_id=str(version.id),
            ), OrchestrationPhase.AGENT)
            status = "completed"
            return response
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except (TaskExecutionError, TaskConfirmationRequired, RuntimeExecutionGuardError) as exc:
            details = exc.details if isinstance(exc, TaskExecutionError) else {}
            diagnostics = {key: details[key] for key in (
                "status_code", "provider_type", "provider_code", "provider_message", "provider_param",
            ) if details.get(key) is not None}
            await self._safe_emit(agent_journal, RuntimeEvent.error(
                "Shadow agent execution failed",
                error_code=getattr(exc, "code", "shadow_confirmation_required"),
                operator_message=details.get("operator_message") or "Shadow agent execution failed",
                **diagnostics,
            ), OrchestrationPhase.AGENT)
            raise ExternalServiceError(
                details.get("user_message") or "Shadow agent execution failed",
                details={"error_code": getattr(exc, "code", "shadow_confirmation_required"),
                         "retryable": bool(getattr(exc, "retryable", False))},
            ) from exc
        except Exception as exc:
            await self._safe_emit(agent_journal, RuntimeEvent.error(
                "Shadow invocation failed", exception_type=type(exc).__name__,
                error_code="shadow_result_invalid" if isinstance(exc, ExternalServiceError) else "shadow_invocation_failed",
            ), OrchestrationPhase.AGENT)
            raise
        finally:
            async def finish_journal() -> None:
                try:
                    await guard.finish()
                except Exception:
                    logger.exception("shadow_guard_finish_failed")
                await self._safe_emit(agent_journal, RuntimeEvent.agent_end(
                    agent_execution_id=str(execution_id), parent_entity_type="run",
                    parent_entity_id=str(run_id), agent_slug=agent.slug,
                    task_id=task.task_id, status=status, outcome=status,
                ), OrchestrationPhase.AGENT)
                await self._safe_emit(journal, RuntimeEvent.run_end(
                    run_id=str(run_id), status=status), OrchestrationPhase.PIPELINE)

            terminal_write = asyncio.create_task(finish_journal())
            try:
                await asyncio.shield(terminal_write)
            except asyncio.CancelledError:
                await asyncio.shield(terminal_write)
                raise

    async def resolve_scope_context(self, request: ShadowAgentRequest, *, user_id: UUID, tenant_id: UUID) -> EffectiveScopeContext:
        preferences = MemoryScopePreferencesService(self.session)
        context = {}
        if request.scope_keys is not None:
            try:
                keys = await preferences.validate_keys(request.scope_keys)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            context = {"focus": {"scope_mode": "replace", "scope_keys": keys}}
        return await preferences.resolve_context(user_id=user_id, tenant_id=tenant_id, chat_context=context)

    @staticmethod
    async def _safe_emit(journal: RuntimeEventLogger, event: RuntimeEvent, phase: OrchestrationPhase) -> None:
        """Journal availability must not replace an invocation result or error."""
        try:
            await journal.emit(event, phase=phase)
        except Exception as exc:
            logger.error("shadow_journal_write_failed event_type=%s error_type=%s",
                         event.type.value, type(exc).__name__)
