"""
RuntimePipeline — единая точка входа для полного цикла выполнения.

Используется как из ChatStreamService, так и из Sandbox.
Убирает дублирование логики между ними.

Flow:
1. Resolve agent slug (tenant default / override)
2. Triage via SystemLLMExecutor (decide: final / clarify / orchestrate)
3. ExecutionPreflight — pre-flight checks (only for orchestrate path)
4. Build helper summary + execution outline
5. Apply overrides (sandbox or runtime)
6. Dispatch to planner runtime
7. Yield RuntimeEvent stream
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.execution_preflight import (
    ExecutionPreflight,
    AgentUnavailableError,
    ExecutionMode,
)
from app.agents.contracts import (
    RuntimePipelineRequest,
    RuntimeTriageDecision,
)
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime_logging_resolver import RuntimeLoggingResolver
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.agents.runtime_trace_logger import RuntimeTraceLogger
from app.agents.runtime.pipeline_use_cases import (
    ExecutePlannerUseCase,
    PrepareExecutionUseCase,
    TriageUseCase,
)
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.services.agent_service import AgentService
from app.services.execution_outline_service import ExecutionOutlineService
from app.services.runtime_access_snapshot_service import RuntimeAccessSnapshotService
from app.services.permission_service import PermissionService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.runtime_helper_summary_service import RuntimeHelperSummaryService
if TYPE_CHECKING:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest
    from app.agents.runtime import AgentRuntime
    from app.core.http.clients import LLMClientProtocol

logger = get_logger(__name__)


class RuntimePipeline:
    """Unified execution pipeline: triage → preflight → dispatch → stream.

    Replaces duplicated logic in ChatStreamService._run_with_router()
    and sandbox.py run_sandbox().
    """

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        runtime: AgentRuntime,
        *,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        trace_logger: Optional[RuntimeTraceLogger] = None,
        logging_resolver: Optional[RuntimeLoggingResolver] = None,
        sandbox_resolver: Optional[RuntimeSandboxResolver] = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.runtime = runtime
        self.sandbox_overrides = sandbox_overrides or {}
        self.trace_logger = trace_logger or RuntimeTraceLogger(
            session=session,
            session_factory=get_session_factory(),
            run_store=runtime.run_store,
            sandbox_overrides=self.sandbox_overrides,
        )
        self.logging_resolver = logging_resolver or RuntimeLoggingResolver()
        self.sandbox_resolver = sandbox_resolver or RuntimeSandboxResolver(session=session)

        # Services — created once per pipeline invocation
        self.agent_service = AgentService(session)
        self.runtime_rbac_resolver = RuntimeRbacResolver(PermissionService(session))
        self.runtime_config_service = RuntimeConfigService(session)
        self.runtime_access_snapshot_service = RuntimeAccessSnapshotService(
            self.runtime_rbac_resolver,
        )
        self.triage_use_case = TriageUseCase(session, llm_client)
        self.execute_planner_use_case = ExecutePlannerUseCase(runtime)
        self._preflight: Optional[ExecutionPreflight] = None
        self.helper_summary_service = RuntimeHelperSummaryService()
        self.execution_outline_service = ExecutionOutlineService()

    @staticmethod
    def _ctx_get_runtime_deps(ctx: "ToolContext") -> Any:
        getter = getattr(ctx, "get_runtime_deps", None)
        if callable(getter):
            try:
                deps = getter()
                if deps is not None:
                    return deps
            except Exception:
                pass
        deps = getattr(ctx, "runtime_deps", None)
        if deps is not None:
            return deps
        return SimpleNamespace(
            operation_executor=None,
            session_factory=None,
            execution_graph=None,
            helper_summary=None,
            execution_outline=None,
        )

    @staticmethod
    def _ctx_set_runtime_deps(ctx: "ToolContext", deps: Any) -> None:
        setter = getattr(ctx, "set_runtime_deps", None)
        if callable(setter):
            setter(deps)
            return
        setattr(ctx, "runtime_deps", deps)

    @property
    def preflight(self) -> ExecutionPreflight:
        if self._preflight is None:
            from app.agents.execution_preflight import ExecutionPreflight as ExecutionPreflightFactory

            self._preflight = ExecutionPreflightFactory(self.session)
        return self._preflight

    async def execute(
        self,
        request_text: str,
        user_id: UUID,
        tenant_id: UUID,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        *,
        agent_slug: Optional[str] = None,
        agent_version_id: Optional[UUID] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Full execution pipeline yielding RuntimeEvents.

        Args:
            request_text: User's request text.
            user_id: User UUID.
            tenant_id: Tenant UUID.
            messages: LLM message history (including current user message).
            ctx: ToolContext with session, overrides, etc.
            agent_slug: Override agent slug (None = resolve from tenant).
            model: Override model (None = resolve from config).
        """
        agent_svc = self.agent_service
        ctx = self.trace_logger.attach_context(ctx)
        runtime_request = RuntimePipelineRequest.model_validate(
            {
                "request_text": request_text,
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "messages": messages,
                "agent_slug": agent_slug,
                "agent_version_id": str(agent_version_id) if agent_version_id else None,
                "model": model,
            }
        )

        # ── 1. Resolve agent slug ────────────────────────────────────────
        effective_slug = runtime_request.agent_slug
        default_agent_slug = await agent_svc.get_default_agent_slug(tenant_id)

        default_slugs = {"assistant", "universal", None, ""}
        if effective_slug in default_slugs:
            effective_slug = default_agent_slug

        agent_log_level = None
        try:
            resolved_agent = await agent_svc.get_agent_by_slug(effective_slug)
            agent_log_level = getattr(resolved_agent, "logging_level", None)
        except Exception as e:
            logger.warning("[Pipeline] Failed to resolve agent logging level for %s: %s", effective_slug, e)

        logging_level = await self.logging_resolver.resolve_logging_level(ctx, agent_log_level)
        enable_logging = logging_level.value != "none"
        pipeline_run = self.trace_logger.make_run_session(
            ctx=ctx,
            agent_slug=effective_slug or "pipeline",
            mode="pipeline",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            chat_id=getattr(ctx, "chat_id", None),
            logging_level=logging_level.value,
            context_snapshot={
                "request_text": request_text[:500],
                "continuation_meta": dict(ctx.extra.get("continuation_meta") or {}),
            },
            enable_logging=enable_logging,
        )
        await pipeline_run.start()
        await pipeline_run.log_step("user_request", {
            "content": request_text[:1000],
            "chat_id": getattr(ctx, "chat_id", None),
            "mode": "pipeline",
        })

        # ── 2. Load platform config (shared by triage + outline) ─────────
        platform_config = await self._load_platform_config()
        platform_ov = self.sandbox_overrides.get("platform", {})
        if platform_ov:
            platform_config.update(platform_ov)
        snapshot = await self.runtime_access_snapshot_service.build_snapshot(
            user_id=user_id,
            tenant_id=tenant_id,
            runtime_config=platform_config,
            agent_service=agent_svc,
        )
        if snapshot.denied_routable_agents:
            await pipeline_run.log_step(
                "rbac_routable_agents_filtered",
                {"denied": sorted(snapshot.denied_routable_agents)},
            )

        # ── 3. Triage ────────────────────────────────────────────────────
        yield RuntimeEvent.status("triage")

        try:
            triage_result = await self._run_triage(
                request_text=runtime_request.request_text,
                messages=runtime_request.messages,
                platform_config=platform_config,
                routable_agents=snapshot.routable_agents,
            )
        except Exception as e:
            triage_result = await self._handle_triage_error(
                error=e,
                request_text=runtime_request.request_text,
                platform_config=platform_config,
                pipeline_run=pipeline_run,
            )
            if triage_result is None:
                yield RuntimeEvent.error(f"Triage failed: {e}")
                return
        triage_result = RuntimeTriageDecision.model_validate(triage_result)

        yield RuntimeEvent(RuntimeEventType.STATUS, {
            "stage": "triage_complete",
            "triage_type": triage_result.type,
            "triage_agent": None,
            "triage_confidence": triage_result.confidence,
        })

        logger.info(
            f"[Pipeline] Triage: type={triage_result.type}, "
            f"agent={None}, "
            f"confidence={triage_result.confidence}"
        )
        await pipeline_run.log_step("triage_complete", {
            "triage_type": triage_result.type,
            "triage_agent": None,
            "triage_confidence": triage_result.confidence,
            "trace_id": str(triage_result.trace_id) if triage_result.trace_id else None,
        })

        # ── 4. Handle triage early exits ─────────────────────────────────

        # 4a. Direct answer from triage
        if triage_result.type == "final" and triage_result.answer:
            answer = triage_result.answer
            await pipeline_run.log_step("final", {
                "source": "triage",
                "answer_preview": answer[:300],
                "answer_length": len(answer),
            })
            await pipeline_run.finish("completed")
            yield RuntimeEvent.status("direct_streaming")
            for i in range(0, len(answer), 20):
                yield RuntimeEvent.delta(answer[i:i + 20])
            yield RuntimeEvent.final(answer, sources=[], run_id=str(pipeline_run.run_id) if pipeline_run.run_id else None)
            return

        # 4b. Clarify path
        if triage_result.type == "clarify":
            question = triage_result.clarify_prompt or "Could you clarify what you want me to do?"
            await pipeline_run.log_step("waiting_input", {
                "source": "triage",
                "question": question,
            })
            await pipeline_run.finish("waiting_input")
            yield RuntimeEvent(RuntimeEventType.WAITING_INPUT, {"question": question})
            yield RuntimeEvent(RuntimeEventType.STOP, {
                "reason": "waiting_input",
                "question": question,
                # Triage clarify happens before AgentRun preflight; no resumable run_id exists here.
                "run_id": None,
            })
            return

        # ── 5. ExecutionPreflight (only orchestrate path) ────────────────
        yield RuntimeEvent.status("preflight")

        try:
            explicit_agent_selected = runtime_request.agent_slug not in default_slugs
            exec_request = await self._prepare_execution(
                agent_slug=effective_slug,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=runtime_request.request_text[:500],
                allow_partial=True,
                agent_version_id=agent_version_id,
                platform_config=platform_config,
                sandbox_overrides=self.sandbox_overrides,
                include_routable_agents=not explicit_agent_selected,
                routable_agents_override=(
                    snapshot.routable_agents if not explicit_agent_selected else None
                ),
                effective_permissions_override=snapshot.effective_permissions,
            )
        except AgentUnavailableError as e:
            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="preflight",
                error=e,
                data={"error_type": "agent_unavailable"},
            )
            await pipeline_run.finish("failed", str(e))
            yield RuntimeEvent.error(str(e))
            return
        except Exception as e:
            handled = await self._handle_preflight_error(
                error=e,
                platform_config=platform_config,
                pipeline_run=pipeline_run,
            )
            if handled:
                yield RuntimeEvent.status("preflight_degraded")
                yield RuntimeEvent.final(
                    self._preflight_fail_open_message(platform_config),
                    sources=[],
                    run_id=str(pipeline_run.run_id) if pipeline_run.run_id else None,
                )
            else:
                yield RuntimeEvent.error(f"Preflight failed: {e}")
            return

        logger.info(
            f"[Pipeline] Preflight: agent={exec_request.agent_slug}, "
            f"mode={exec_request.mode.value}, operations={len(exec_request.resolved_operations)}"
        )
        await pipeline_run.log_step("preflight_complete", {
            "agent": exec_request.agent_slug,
            "mode": exec_request.mode.value,
            "available_operations": [
                operation.operation_slug
                for operation in exec_request.resolved_operations
            ],
        })

        yield RuntimeEvent(RuntimeEventType.STATUS, {
            "stage": "preflight_complete",
            "agent": exec_request.agent_slug,
            "mode": exec_request.mode.value,
            "available_operations": [
                operation.operation_slug
                for operation in exec_request.resolved_operations
            ],
        })

        # ── 6. Check availability ────────────────────────────────────────
        if exec_request.mode == ExecutionMode.UNAVAILABLE:
            missing = exec_request.missing_requirements
            msg = f"Agent unavailable: {missing.to_message()}" if missing else "Agent unavailable"
            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="availability",
                error=msg,
                data={"error_type": "agent_unavailable"},
            )
            await pipeline_run.finish("failed", msg)
            yield RuntimeEvent.error(msg)
            return

        # Enrich runtime dependencies in context.
        runtime_deps = self._ctx_get_runtime_deps(ctx)
        runtime_deps.operation_executor = DirectOperationExecutor()
        if not getattr(runtime_deps, "session_factory", None):
            try:
                runtime_deps.session_factory = get_session_factory()
            except RuntimeError:
                runtime_deps.session_factory = None
        if getattr(exec_request, "execution_graph", None):
            runtime_deps.execution_graph = exec_request.execution_graph
        self._ctx_set_runtime_deps(ctx, runtime_deps)
        if exec_request.effective_permissions:
            denied_reasons = exec_request.effective_permissions.denied_reasons or {}
            ctx.denied_tools = list(denied_reasons.keys())
            ctx.denied_reasons = denied_reasons

        # ── 7. Build outline ─────────────────────────────────────────────
        helper_summary = self.helper_summary_service.build(request_text=request_text, messages=messages)
        execution_outline = self.execution_outline_service.build(
            request_text=request_text,
            triage_result=triage_result.model_dump(),
            available_agent_slugs=[agent.agent_slug for agent in exec_request.available_actions.agents] if exec_request.available_actions else [],
            platform_config=platform_config,
        )
        runtime_deps = self._ctx_get_runtime_deps(ctx)
        runtime_deps.helper_summary = helper_summary.model_dump()
        runtime_deps.execution_outline = execution_outline.model_dump()
        self._ctx_set_runtime_deps(ctx, runtime_deps)
        # Keep backward-compat for components/tests reading from ctx.extra directly.
        if isinstance(getattr(ctx, "extra", None), dict):
            ctx.extra["helper_summary"] = runtime_deps.helper_summary
            ctx.extra["execution_outline"] = runtime_deps.execution_outline

        yield RuntimeEvent(RuntimeEventType.STATUS, {
            "stage": "outline_ready",
            "outline_mode": execution_outline.mode.value,
            "outline_phases": [phase.phase_id for phase in execution_outline.phases],
        })

        # ── 8. Orchestrate via planner ─────────────────────────────────
        logger.info("[Pipeline] Execution path: planner (orchestrate)")
        yield RuntimeEvent.status("executing_planner")

        planner_status = "completed"
        planner_error: Optional[str] = None
        try:
            try:
                async for event in self.execute_planner_use_case.execute(
                    exec_request=exec_request,
                    messages=messages,
                    ctx=ctx,
                    model=runtime_request.model,
                    enable_logging=enable_logging,
                ):
                    if event.type == RuntimeEventType.FINAL:
                        event.data.setdefault("run_id", str(exec_request.run_id))
                        planner_status = "completed"
                    elif event.type == RuntimeEventType.STOP:
                        reason = str(event.data.get("reason") or "")
                        planner_status = reason or "stopped"
                        planner_error = str(event.data.get("message") or event.data.get("question") or "")
                    elif event.type == RuntimeEventType.ERROR:
                        planner_status = "failed"
                        planner_error = str(event.data.get("error") or "runtime_error")
                    yield event
            except Exception as e:
                handled = await self._handle_planner_error(
                    error=e,
                    platform_config=platform_config,
                    exec_request=exec_request,
                    pipeline_run=pipeline_run,
                )
                if handled:
                    planner_status = "completed"
                    planner_error = None
                    yield RuntimeEvent.status("planner_degraded")
                    yield RuntimeEvent.final(
                        self._planner_fail_open_message(platform_config),
                        sources=[],
                        run_id=str(exec_request.run_id),
                    )
                else:
                    planner_status = "failed"
                    planner_error = str(e)
                    yield RuntimeEvent.error(f"Planner failed: {e}")
        finally:
            await pipeline_run.finish(planner_status, planner_error or None)

    # ── Internal: Triage ─────────────────────────────────────────────────

    async def _run_triage(
        self,
        request_text: str,
        messages: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        routable_agents: Optional[List[Any]] = None,
    ) -> RuntimeTriageDecision:
        """Compatibility shim for tests; delegates to TriageUseCase."""
        return await self.triage_use_case.execute(
            request_text=request_text,
            messages=messages,
            platform_config=platform_config,
            routable_agents=routable_agents,
        )

    async def _prepare_execution(
        self,
        *,
        agent_slug: str,
        user_id: UUID,
        tenant_id: UUID,
        request_text: str,
        allow_partial: bool,
        agent_version_id: Optional[UUID],
        platform_config: Dict[str, Any],
        sandbox_overrides: Dict[str, Any],
        include_routable_agents: bool,
        routable_agents_override: Optional[List[Any]],
        effective_permissions_override: Optional[Any],
    ) -> ExecutionRequest:
        return await PrepareExecutionUseCase(self.preflight).execute(
            agent_slug=agent_slug,
            user_id=user_id,
            tenant_id=tenant_id,
            request_text=request_text,
            allow_partial=allow_partial,
            agent_version_id=agent_version_id,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
            include_routable_agents=include_routable_agents,
            routable_agents_override=routable_agents_override,
            effective_permissions_override=effective_permissions_override,
        )

    @staticmethod
    def _triage_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        # Explicit fail policy for triage stage.
        return bool((platform_config or {}).get("triage_fail_open", True))

    async def _handle_triage_error(
        self,
        *,
        error: Exception,
        request_text: str,
        platform_config: Dict[str, Any],
        pipeline_run: Any,
    ) -> Optional[RuntimeTriageDecision]:
        if self._triage_fail_open_enabled(platform_config):
            logger.warning("[Pipeline] Triage failed (fail-open): %s", error)
            await pipeline_run.log_step(
                "triage_fallback_orchestrate",
                {"error": str(error), "policy": "fail_open"},
            )
            return RuntimeTriageDecision(
                type="orchestrate",
                confidence=0.0,
                goal=request_text,
                inputs={},
            )

        logger.error("[Pipeline] Triage failed (fail-closed): %s", error, exc_info=True)
        await self.trace_logger.log_error(
            pipeline_run.run_id,
            stage="triage",
            error=error,
            data={"error_type": "triage_error", "policy": "fail_closed"},
        )
        await pipeline_run.finish("failed", str(error))
        return None

    @staticmethod
    def _preflight_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        return bool((platform_config or {}).get("preflight_fail_open", False))

    @staticmethod
    def _planner_fail_open_enabled(platform_config: Dict[str, Any]) -> bool:
        return bool((platform_config or {}).get("planner_fail_open", False))

    @staticmethod
    def _preflight_fail_open_message(platform_config: Dict[str, Any]) -> str:
        msg = str((platform_config or {}).get("preflight_fail_open_message") or "").strip()
        if msg:
            return msg
        return (
            "Не удалось подготовить выполнение с инструментами. "
            "Сформулируйте запрос иначе или обратитесь к администратору."
        )

    @staticmethod
    def _planner_fail_open_message(platform_config: Dict[str, Any]) -> str:
        msg = str((platform_config or {}).get("planner_fail_open_message") or "").strip()
        if msg:
            return msg
        return (
            "Во время выполнения произошла ошибка планировщика. "
            "Попробуйте повторить запрос позже."
        )

    async def _handle_preflight_error(
        self,
        *,
        error: Exception,
        platform_config: Dict[str, Any],
        pipeline_run: Any,
    ) -> bool:
        if self._preflight_fail_open_enabled(platform_config):
            logger.warning("[Pipeline] Preflight failed (fail-open): %s", error)
            await pipeline_run.log_step(
                "preflight_fallback_final",
                {"error": str(error), "policy": "fail_open"},
            )
            await pipeline_run.finish("completed")
            return True

        await self.trace_logger.log_error(
            pipeline_run.run_id,
            stage="preflight",
            error=error,
            data={"error_type": "preflight_error", "policy": "fail_closed"},
        )
        await pipeline_run.finish("failed", str(error))
        return False

    async def _handle_planner_error(
        self,
        *,
        error: Exception,
        platform_config: Dict[str, Any],
        exec_request: ExecutionRequest,
        pipeline_run: Any,
    ) -> bool:
        if self._planner_fail_open_enabled(platform_config):
            logger.warning("[Pipeline] Planner failed (fail-open): %s", error)
            await pipeline_run.log_step(
                "planner_fallback_final",
                {"error": str(error), "policy": "fail_open"},
            )
            return True

        await self.trace_logger.log_error(
            pipeline_run.run_id,
            stage="planner",
            error=error,
            data={
                "error_type": "planner_error",
                "policy": "fail_closed",
                "run_id": str(exec_request.run_id),
            },
        )
        return False

    async def _load_platform_config(self) -> Dict[str, Any]:
        """Load effective pipeline config via dedicated runtime config service."""
        return await self.runtime_config_service.get_pipeline_config()
