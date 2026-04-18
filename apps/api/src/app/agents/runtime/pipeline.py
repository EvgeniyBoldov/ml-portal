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
    ExecutionMode,
)
from app.agents.contracts import (
    RuntimePipelineRequest,
    RuntimeTriageDecision,
)
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
from app.services.orchestration_context_builder import OrchestrationContextBuilder
from app.services.orchestration_contract import (
    OrchestrationPhase,
    attach_orchestration_envelope,
)
from app.services.runtime_access_snapshot_service import RuntimeAccessSnapshotService
from app.services.runtime_planner_orchestrator import RuntimePlannerOrchestrator
from app.services.runtime_preflight_orchestrator import RuntimePreflightOrchestrator
from app.services.runtime_preparation_orchestrator import RuntimePreparationOrchestrator
from app.services.permission_service import PermissionService
from app.services.runtime_config_service import RuntimeConfigService
from app.services.runtime_helper_summary_service import RuntimeHelperSummaryService
from app.services.runtime_triage_orchestrator import RuntimeTriageOrchestrator
from app.services.orchestration_state_store import OrchestrationStateStore
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
        self.orchestration_context_builder = OrchestrationContextBuilder(
            self.runtime_access_snapshot_service,
        )
        self.triage_orchestrator = RuntimeTriageOrchestrator(self.trace_logger)
        self.preflight_orchestrator = RuntimePreflightOrchestrator(self.trace_logger)
        self.preparation_orchestrator = RuntimePreparationOrchestrator()
        self.planner_orchestrator = RuntimePlannerOrchestrator(self.trace_logger)
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

        default_slugs = {"assistant", "universal", None, ""}
        orchestration_ctx = await self.orchestration_context_builder.build(
            request_text=runtime_request.request_text,
            user_id=user_id,
            tenant_id=tenant_id,
            requested_agent_slug=runtime_request.agent_slug,
            default_slugs=default_slugs,
            sandbox_overrides=self.sandbox_overrides,
            agent_service=agent_svc,
            load_platform_config=self._load_platform_config,
        )
        effective_slug = orchestration_ctx.effective_agent_slug

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
        try:
            state_store = OrchestrationStateStore(get_session_factory())
        except RuntimeError:
            state_store = None
        state_run_id = getattr(pipeline_run, "run_id", None)
        if state_store and state_run_id:
            state = await state_store.update(
                state_run_id,
                chat_id=str(getattr(ctx, "chat_id", "") or "") or None,
                tenant_id=str(tenant_id),
                goal=request_text,
                patch={
                    "run_id": str(state_run_id),
                    "request_text": request_text,
                    "run_status": "running",
                    "meta": {"stage": "pipeline_started"},
                },
            )
            if state and isinstance(getattr(ctx, "extra", None), dict):
                ctx.extra["orchestration_state"] = state.model_dump()
        event_seq = 0

        def _orchestration_state_view() -> Optional[Dict[str, Any]]:
            raw = None
            if isinstance(getattr(ctx, "extra", None), dict):
                raw = ctx.extra.get("orchestration_state")
            if not isinstance(raw, dict):
                return None
            open_questions = raw.get("open_questions")
            if isinstance(open_questions, list):
                open_questions = [str(item) for item in open_questions][-3:]
            else:
                open_questions = []
            return {
                "run_status": raw.get("run_status"),
                "intent_type": raw.get("intent_type"),
                "current_phase_id": raw.get("current_phase_id"),
                "current_agent_slug": raw.get("current_agent_slug"),
                "open_questions": open_questions,
            }

        def _with_env(event: RuntimeEvent, phase: OrchestrationPhase, run_id: Optional[str] = None) -> RuntimeEvent:
            nonlocal event_seq
            event_seq += 1
            enriched = attach_orchestration_envelope(
                event,
                phase=phase,
                sequence=event_seq,
                run_id=run_id or (str(pipeline_run.run_id) if pipeline_run.run_id else None),
                chat_id=str(getattr(ctx, "chat_id", "") or "") or None,
            )
            state_view = _orchestration_state_view()
            if state_view and isinstance(enriched.data, dict):
                enriched.data["orchestration_state"] = state_view
            return enriched

        # ── 2. Load platform config (shared by triage + outline) ─────────
        platform_config = orchestration_ctx.platform_config
        snapshot = orchestration_ctx.snapshot
        if snapshot.denied_routable_agents:
            await pipeline_run.log_step(
                "rbac_routable_agents_filtered",
                {"denied": sorted(snapshot.denied_routable_agents)},
            )

        # ── 3. Triage ────────────────────────────────────────────────────
        yield _with_env(RuntimeEvent.status("triage"), OrchestrationPhase.TRIAGE)

        triage_result = await self.triage_orchestrator.execute(
            run_triage=self._run_triage,
            request_text=runtime_request.request_text,
            messages=runtime_request.messages,
            platform_config=platform_config,
            routable_agents=snapshot.routable_agents,
            pipeline_run=pipeline_run,
        )
        if triage_result is None:
            yield _with_env(RuntimeEvent.error("Triage failed"), OrchestrationPhase.TRIAGE)
            return

        yield _with_env(
            RuntimeEvent(RuntimeEventType.STATUS, {
                "stage": "triage_complete",
                "triage_type": triage_result.type,
                "triage_agent": None,
                "triage_confidence": triage_result.confidence,
            }),
            OrchestrationPhase.TRIAGE,
        )

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
        if state_store and state_run_id:
            state = await state_store.update(
                state_run_id,
                goal=triage_result.goal or request_text,
                patch={
                    "intent_type": triage_result.type,
                    "run_status": "triage_complete",
                    "meta": {
                        "stage": "triage_complete",
                        "triage_confidence": triage_result.confidence,
                    },
                },
            )
            if state and isinstance(getattr(ctx, "extra", None), dict):
                ctx.extra["orchestration_state"] = state.model_dump()

        # ── 4. Handle triage early exits ─────────────────────────────────

        # 4a. Direct answer from triage
        if triage_result.type == "final" and triage_result.answer:
            answer = triage_result.answer
            await pipeline_run.log_step("final", {
                "source": "triage",
                "answer_preview": answer[:300],
                "answer_length": len(answer),
            })
            if state_store and state_run_id:
                state = await state_store.update(
                    state_run_id,
                    patch={"run_status": "completed", "meta": {"stage": "triage_final"}},
                )
                if state and isinstance(getattr(ctx, "extra", None), dict):
                    ctx.extra["orchestration_state"] = state.model_dump()
            await pipeline_run.finish("completed")
            yield _with_env(RuntimeEvent.status("direct_streaming"), OrchestrationPhase.TRIAGE)
            for i in range(0, len(answer), 20):
                yield _with_env(RuntimeEvent.delta(answer[i:i + 20]), OrchestrationPhase.TRIAGE)
            yield _with_env(
                RuntimeEvent.final(answer, sources=[], run_id=str(pipeline_run.run_id) if pipeline_run.run_id else None),
                OrchestrationPhase.TRIAGE,
            )
            return

        # 4b. Clarify path
        if triage_result.type == "clarify":
            question = triage_result.clarify_prompt or "Could you clarify what you want me to do?"
            await pipeline_run.log_step("waiting_input", {
                "source": "triage",
                "question": question,
            })
            await pipeline_run.finish("waiting_input")
            if state_store and state_run_id:
                state = await state_store.update(
                    state_run_id,
                    patch={
                        "run_status": "waiting_input",
                        "open_questions": [question],
                        "meta": {"stage": "triage_clarify"},
                    },
                )
                if state and isinstance(getattr(ctx, "extra", None), dict):
                    ctx.extra["orchestration_state"] = state.model_dump()
            yield _with_env(RuntimeEvent(RuntimeEventType.WAITING_INPUT, {"question": question}), OrchestrationPhase.TRIAGE)
            yield _with_env(
                RuntimeEvent(RuntimeEventType.STOP, {
                    "reason": "waiting_input",
                    "question": question,
                    # Triage clarify happens before AgentRun preflight; no resumable run_id exists here.
                    "run_id": None,
                }),
                OrchestrationPhase.TRIAGE,
            )
            return

        # ── 5. ExecutionPreflight (only orchestrate path) ────────────────
        yield _with_env(RuntimeEvent.status("preflight"), OrchestrationPhase.PIPELINE)

        explicit_agent_selected = runtime_request.agent_slug not in default_slugs
        preflight_outcome = await self.preflight_orchestrator.execute(
            prepare_execution=self._prepare_execution,
            prepare_kwargs={
                "agent_slug": effective_slug,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "request_text": runtime_request.request_text[:500],
                "allow_partial": True,
                "agent_version_id": agent_version_id,
                "platform_config": platform_config,
                "sandbox_overrides": self.sandbox_overrides,
                "include_routable_agents": not explicit_agent_selected,
                "routable_agents_override": (
                    snapshot.routable_agents if not explicit_agent_selected else None
                ),
                "effective_permissions_override": snapshot.effective_permissions,
            },
            platform_config=platform_config,
            pipeline_run=pipeline_run,
        )
        if preflight_outcome.should_stop:
            for event in preflight_outcome.events:
                yield _with_env(event, OrchestrationPhase.PIPELINE)
            return
        exec_request = preflight_outcome.exec_request
        if exec_request is None:
            yield _with_env(RuntimeEvent.error("Preflight failed: empty execution request"), OrchestrationPhase.PIPELINE)
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
        if state_store and state_run_id:
            state = await state_store.update(
                state_run_id,
                current_agent_slug=exec_request.agent_slug,
                patch={
                    "run_status": "preflight_complete",
                    "meta": {
                        "stage": "preflight_complete",
                        "mode": exec_request.mode.value,
                        "available_operations": len(exec_request.resolved_operations),
                    },
                },
            )
            if state and isinstance(getattr(ctx, "extra", None), dict):
                ctx.extra["orchestration_state"] = state.model_dump()

        yield _with_env(
            RuntimeEvent(RuntimeEventType.STATUS, {
                "stage": "preflight_complete",
                "agent": exec_request.agent_slug,
                "mode": exec_request.mode.value,
                "available_operations": [
                    operation.operation_slug
                    for operation in exec_request.resolved_operations
                ],
            }),
            OrchestrationPhase.PIPELINE,
        )

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
            yield _with_env(RuntimeEvent.error(msg), OrchestrationPhase.PIPELINE)
            return

        # ── 7. Prepare runtime deps + build outline ──────────────────────
        prep = self.preparation_orchestrator.prepare(
            request_text=request_text,
            messages=messages,
            triage_result=triage_result,
            platform_config=platform_config,
            exec_request=exec_request,
            ctx=ctx,
            ctx_get_runtime_deps=self._ctx_get_runtime_deps,
            ctx_set_runtime_deps=self._ctx_set_runtime_deps,
            get_session_factory=get_session_factory,
            helper_summary_service=self.helper_summary_service,
            execution_outline_service=self.execution_outline_service,
        )
        execution_outline = prep.execution_outline
        if state_store and state_run_id:
            outline_phase_ids = [phase.phase_id for phase in execution_outline.phases]
            state = await state_store.update(
                state_run_id,
                current_phase_id=outline_phase_ids[0] if outline_phase_ids else None,
                patch={
                    "run_status": "outline_ready",
                    "meta": {
                        "stage": "outline_ready",
                        "outline_mode": execution_outline.mode.value,
                        "outline_phases": outline_phase_ids,
                    },
                },
            )
            if state and isinstance(getattr(ctx, "extra", None), dict):
                ctx.extra["orchestration_state"] = state.model_dump()
        yield _with_env(prep.outline_event, OrchestrationPhase.PIPELINE)

        # ── 8. Orchestrate via planner ─────────────────────────────────
        logger.info("[Pipeline] Execution path: planner (orchestrate)")
        yield _with_env(RuntimeEvent.status("executing_planner"), OrchestrationPhase.PLANNER)

        try:
            async for event in self.planner_orchestrator.stream(
                execute_planner_use_case=self.execute_planner_use_case,
                exec_request=exec_request,
                messages=messages,
                ctx=ctx,
                model=runtime_request.model,
                enable_logging=enable_logging,
                platform_config=platform_config,
                pipeline_run=pipeline_run,
                state_store=state_store,
                state_chat_id=str(getattr(ctx, "chat_id", "") or "") or None,
                state_tenant_id=str(tenant_id),
            ):
                yield _with_env(event, OrchestrationPhase.PLANNER, run_id=str(exec_request.run_id))
        finally:
            await pipeline_run.finish(
                self.planner_orchestrator.last_status,
                self.planner_orchestrator.last_error or None,
            )
            if state_store and state_run_id:
                state = await state_store.update(
                    state_run_id,
                    patch={
                        "run_status": self.planner_orchestrator.last_status,
                        "meta": {
                            "stage": "planner_finished",
                            "planner_error": self.planner_orchestrator.last_error,
                        },
                    },
                )
                if state and isinstance(getattr(ctx, "extra", None), dict):
                    ctx.extra["orchestration_state"] = state.model_dump()

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

    async def _load_platform_config(self) -> Dict[str, Any]:
        """Load effective pipeline config via dedicated runtime config service."""
        return await self.runtime_config_service.get_pipeline_config()
