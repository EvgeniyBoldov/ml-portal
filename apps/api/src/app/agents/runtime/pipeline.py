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
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime_logging_resolver import RuntimeLoggingResolver
from app.agents.runtime_sandbox_resolver import RuntimeSandboxResolver
from app.agents.runtime_trace_logger import RuntimeTraceLogger
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.services.agent_service import AgentService
from app.services.execution_outline_service import ExecutionOutlineService
from app.services.platform_settings_service import PlatformSettingsProvider
from app.services.runtime_helper_summary_service import RuntimeHelperSummaryService
from app.services.system_llm_executor import SystemLLMExecutor
from app.schemas.system_llm_roles import TriageInput

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

        # ── 1. Resolve agent slug ────────────────────────────────────────
        effective_slug = agent_slug
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

        # ── 3. Triage ────────────────────────────────────────────────────
        yield RuntimeEvent.status("triage")

        triage_result = await self._run_triage(
            request_text=request_text,
            messages=messages,
            agent_svc=agent_svc,
            default_agent_slug=default_agent_slug,
            platform_config=platform_config,
        )

        yield RuntimeEvent(RuntimeEventType.STATUS, {
            "stage": "triage_complete",
            "triage_type": triage_result["type"],
            "triage_agent": triage_result.get("agent_slug"),
            "triage_confidence": triage_result.get("confidence"),
        })

        logger.info(
            f"[Pipeline] Triage: type={triage_result['type']}, "
            f"agent={triage_result.get('agent_slug')}, "
            f"confidence={triage_result.get('confidence')}"
        )
        await pipeline_run.log_step("triage_complete", {
            "triage_type": triage_result["type"],
            "triage_agent": triage_result.get("agent_slug"),
            "triage_confidence": triage_result.get("confidence"),
            "trace_id": str(triage_result.get("trace_id")) if triage_result.get("trace_id") else None,
        })

        # ── 4. Handle triage early exits ─────────────────────────────────

        # 4a. Direct answer from triage
        if triage_result["type"] == "final" and triage_result.get("answer"):
            answer = triage_result["answer"]
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
        if triage_result["type"] == "clarify":
            question = triage_result.get("clarify_prompt") or "Could you clarify what you want me to do?"
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
            explicit_agent_selected = agent_slug not in default_slugs
            exec_request = await self.preflight.prepare(
                agent_slug=effective_slug,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=request_text[:500],
                allow_partial=True,
                agent_version_id=agent_version_id,
                platform_config=platform_config,
                sandbox_overrides=self.sandbox_overrides,
                include_routable_agents=not explicit_agent_selected,
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
            await self.trace_logger.log_error(
                pipeline_run.run_id,
                stage="preflight",
                error=e,
                data={"error_type": "preflight_error"},
            )
            await pipeline_run.finish("failed", str(e))
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
            triage_result=triage_result,
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
            async for event in self.runtime.run_sequential_planner(
                exec_request=exec_request,
                messages=messages,
                ctx=ctx,
                model=model,
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
        finally:
            await pipeline_run.finish(planner_status, planner_error or None)

    # ── Internal: Triage ─────────────────────────────────────────────────

    async def _run_triage(
        self,
        request_text: str,
        messages: List[Dict[str, Any]],
        agent_svc: AgentService,
        default_agent_slug: str,
        platform_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run triage and return result dict.

        Returns:
            {"type": "final"|"clarify"|"orchestrate",
             "confidence": float,
             "answer": str|None,
             "clarify_prompt": str|None,
             "goal": str|None}
        """
        try:
            executor = SystemLLMExecutor(self.session, self.llm_client)
            policies_text = platform_config.get("policies_text") or "default"

            # Conversation context
            conversation_parts = []
            for m in messages[-5:]:
                content = m.get("content", "")
                if isinstance(content, dict):
                    content = content.get("text", str(content))
                conversation_parts.append(str(content))

            # Routable agents
            routable_agents = await agent_svc.list_routable_agents()
            agents_list = [
                {"slug": ag.slug, "name": ag.name, "description": ag.description or ""}
                for ag in routable_agents
            ]

            triage_input = TriageInput(
                user_message=request_text,
                conversation_summary="\n".join(conversation_parts[-3:]),
                session_state={"status": "active"},
                available_agents=agents_list,
                policies=policies_text,
                active_run=None,
            )

            triage_result, trace_id = await executor.execute_triage(triage_input)

            return {
                "type": triage_result.type,
                "confidence": triage_result.confidence,
                "answer": getattr(triage_result, "answer", None),
                "clarify_prompt": getattr(triage_result, "clarify_prompt", None),
                "goal": getattr(triage_result, "goal", None),
                "inputs": getattr(triage_result, "inputs", None),
                "trace_id": trace_id,
            }

        except Exception as e:
            logger.warning(f"[Pipeline] Triage failed: {e}, falling back to orchestrate path")
            return {
                "type": "orchestrate",
                "confidence": 0.0,
                "answer": None,
                "clarify_prompt": None,
                "goal": request_text,
                "inputs": {},
            }

    async def _load_platform_config(self) -> Dict[str, Any]:
        """Load platform config with a safe fallback for partial/test environments."""
        try:
            return await PlatformSettingsProvider.get_instance().get_config(self.session)
        except Exception as e:
            error_text = str(e)
            if isinstance(e, AttributeError) and "coroutine" in error_text:
                logger.warning("[Pipeline] Failed to load platform config, using defaults: %s", e)
                return {}
            logger.error("[Pipeline] Failed to load platform config", exc_info=True)
            raise RuntimeError("Failed to load platform config") from e
