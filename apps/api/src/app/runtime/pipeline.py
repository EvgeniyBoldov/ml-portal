"""
RuntimePipeline — thin coordinator (no triage).

Responsibilities (and NOTHING else):
    1. Resolve tenant/user/chat ids from the incoming request.
    2. Load the platform snapshot (config + routable agents + policy).
    3. Ask `MemoryBuilder` to assemble the turn's memory from the
       persisted FactStore + SummaryStore.
    4. Initialize `RuntimeTurnState` as the single source of truth.
    5. Run the PlanningStage — single decision engine:
           DIRECT_ANSWER → planner streamed answer, outcome=DIRECT
           CLARIFY/ASK_USER → pause (waiting_input)
           CALL_AGENT loop → eventually FINAL / ABORT / max_iters
    6. Run FinalizationStage for NEEDS_FINAL outcomes (synthesizer).
    7. Hand off to `MemoryWriter.finalize` to persist extracted facts
       and the updated DialogueSummary for next-turn memory.

Triage is gone. The planner absorbs direct_answer + clarify. The
rolling summary job is delegated to MemoryWriter + SummaryCompactor.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.runtime.logging import LoggingConfig, LoggingLevel
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot, serialize_limits
from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.entity_ids import (
    memory_component_entity_id as _memory_component_entity_id,
    memory_orchestrator_id as _memory_orchestrator_id,
    planner_orchestrator_id,
)
from app.runtime.event_emitter import RuntimeEventEmitter
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.memory.fact_extractor import AgentResultSnippet
from app.runtime.memory.transport import TurnMemory
from app.runtime.platform_config import PlatformConfigLoader
from app.runtime.stages.planning_stage import PlanningOutcomeKind
from app.runtime.turn_state import RuntimeTurnState
from app.core.prometheus_metrics import memory_writer_finalize_failures_total
from app.models.system_llm_role import SystemLLMRoleType
from app.services.agent_service import AgentService
from app.services.permission_service import PermissionService
from app.services.run_store import RunStore
from app.services.system_llm_role_service import SystemLLMRoleService

# Memory writeback runs via Celery (single canonical execution mode).
RUNTIME_MEMORY_INLINE = False

logger = get_logger(__name__)


def _extract_resume_checkpoint(request: PipelineRequest) -> Optional[Dict[str, Any]]:
    continuation_meta = request.continuation_meta if isinstance(request.continuation_meta, dict) else {}
    checkpoint = continuation_meta.get("resume_checkpoint")
    return checkpoint if isinstance(checkpoint, dict) else None


def _extract_effective_goal(request: PipelineRequest, checkpoint: Optional[Dict[str, Any]]) -> str:
    if isinstance(checkpoint, dict):
        for key in ("original_goal", "original_user_request"):
            value = str(checkpoint.get(key) or "").strip()
            if value:
                return value

        source_snapshot = checkpoint.get("source_context_snapshot")
        if isinstance(source_snapshot, dict):
            source_inputs = source_snapshot.get("inputs")
            if isinstance(source_inputs, dict):
                for key in ("goal", "user_request"):
                    value = str(source_inputs.get(key) or "").strip()
                    if value:
                        return value

    return str(request.request_text or "").strip()


def _build_continuation_state(
    request: PipelineRequest,
    checkpoint: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(checkpoint, dict):
        return {}

    paused_action = checkpoint.get("paused_action") if isinstance(checkpoint.get("paused_action"), dict) else {}
    paused_context = checkpoint.get("paused_context") if isinstance(checkpoint.get("paused_context"), dict) else {}
    resumed_from_run_id = ""
    continuation_meta = request.continuation_meta if isinstance(request.continuation_meta, dict) else {}
    if continuation_meta.get("resumed_from_run_id"):
        resumed_from_run_id = str(continuation_meta.get("resumed_from_run_id"))
    elif checkpoint.get("source_run_id"):
        resumed_from_run_id = str(checkpoint.get("source_run_id"))

    original_goal = _extract_effective_goal(request, checkpoint)
    structured: Dict[str, Any] = {
        "mode": "resume",
        "resume_action": str(checkpoint.get("resume_action") or "").strip(),
        "resumed_from_run_id": resumed_from_run_id,
        "original_goal": original_goal,
        "paused_action": paused_action,
        "paused_context": paused_context,
        "user_response": str(checkpoint.get("user_input") or request.request_text or "").strip(),
    }
    source_snapshot = checkpoint.get("source_context_snapshot")
    if isinstance(source_snapshot, dict) and source_snapshot:
        structured["source_context_snapshot"] = source_snapshot
    return {key: value for key, value in structured.items() if value not in ("", None, [], {})}


def _extract_effective_user_query(request: PipelineRequest, checkpoint: Optional[Dict[str, Any]]) -> str:
    if isinstance(checkpoint, dict):
        user_input = str(checkpoint.get("user_input") or "").strip()
        if user_input:
            return user_input
        resume_action = str(checkpoint.get("resume_action") or "").strip().lower()
        if resume_action == "confirm":
            return "[confirmation]"
        if resume_action == "cancel":
            return "[cancel]"
    return str(request.request_text or "").strip()


def _build_question_answer_event(
    *,
    run_id: str,
    orchestrator_id: str,
    checkpoint: Optional[Dict[str, Any]],
) -> Optional[RuntimeEvent]:
    if not isinstance(checkpoint, dict):
        return None

    resume_action = str(checkpoint.get("resume_action") or "").strip().lower()
    if resume_action not in {"input", "confirm"}:
        return None

    paused_action = checkpoint.get("paused_action") if isinstance(checkpoint.get("paused_action"), dict) else {}
    paused_context = checkpoint.get("paused_context") if isinstance(checkpoint.get("paused_context"), dict) else {}

    question = str(
        paused_context.get("question")
        or paused_action.get("question")
        or paused_context.get("message")
        or paused_action.get("message")
        or ""
    ).strip()
    user_answer = str(checkpoint.get("user_input") or "").strip()
    if resume_action == "confirm" and not user_answer:
        user_answer = "Подтверждено"

    question_kind = "confirm" if resume_action == "confirm" else "clarify"
    source_run_id = str(checkpoint.get("source_run_id") or "").strip() or None

    return RuntimeEvent.question_answer(
        interaction_id=f"{run_id}:question-answer",
        parent_entity_id=orchestrator_id,
        resume_action=resume_action,
        question=question or None,
        user_answer=user_answer or None,
        source_run_id=source_run_id,
        question_kind=question_kind,
    )


class RuntimePipeline:
    """Coordinator. Stateless between turns; all turn state lives in
    per-turn state objects built by the assembler."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self._session = session
        self._run_store = run_store
        self._assembler = PipelineAssembler(
            session=session, llm_client=llm_client, run_store=run_store,
        )

    # ------------------------------------------------------------------ #
    # Public entrypoint                                                  #
    # ------------------------------------------------------------------ #

    async def execute(
        self,
        request: PipelineRequest,
        ctx: ToolContext,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        self._apply_sandbox_overrides(request, ctx)
        if request.confirmation_tokens:
            ctx.extra["confirmation_tokens"] = list(request.confirmation_tokens)
        chat_id: Optional[UUID] = UUID(request.chat_id) if request.chat_id else None
        user_id = UUID(request.user_id)
        tenant_id = UUID(request.tenant_id)

        # EventEnvelopeStamper is stateful per execute (carries chat_id for envelope stamping).
        # Per-execute creation is OK; the stamper has no heavy initialization cost.
        envelope = EventEnvelopeStamper(chat_id=request.chat_id)
        platform = await PlatformConfigLoader(self._session).load()
        resume_checkpoint = _extract_resume_checkpoint(request)
        effective_goal = _extract_effective_goal(request, resume_checkpoint)
        continuation_state = _build_continuation_state(request, resume_checkpoint)
        effective_user_query = _extract_effective_user_query(request, resume_checkpoint)

        # --- RBAC resolve FIRST (before memory build) -----------------
        # If agent_slug is denied by RBAC, we treat it as None (fallback to default)
        explicit_slug = request.agent_slug
        available_agents, planner_rbac_audit = await self._resolve_available_agents_for_planner(
            platform=platform,
            explicit_slug=explicit_slug,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        # Sanitize: only allow agent_slug if it's in available_agents
        effective_agent_slug = explicit_slug if explicit_slug in available_agents else None

        # --- Memory: read path ----------------------------------------
        attachment_ids, attachments_dropped = _extract_attachment_ids(request.messages)
        turn_mem = await self._assembler.memory_builder.build(
            goal=effective_goal,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            messages=list(request.messages or []),
            agent_slug=effective_agent_slug,  # RBAC-sanitized
            attachment_ids=attachment_ids,
            platform_config=platform.config,
            sandbox_overrides=request.sandbox_overrides,
        )
        if attachments_dropped:
            turn_mem.memory_diagnostics = dict(turn_mem.memory_diagnostics or {})
            turn_mem.memory_diagnostics["attachments_dropped_count"] = attachments_dropped

        # Initialize RuntimeTurnState as the single source of truth
        # For resume, use the original run_id; otherwise generate new
        resumed_from_run_id = continuation_state.get("resumed_from_run_id") if isinstance(continuation_state, dict) else None
        if resumed_from_run_id:
            try:
                run_id = UUID(resumed_from_run_id)
            except ValueError:
                run_id = uuid4()
        else:
            run_id = uuid4()

        run_logging_level = await self._resolve_run_logging_level(ctx)

        runtime_state = RuntimeTurnState.from_seed(
            run_id=run_id,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            goal=effective_goal,
            current_user_query=effective_user_query,
            memory_bundle=turn_mem.memory_bundle,
            continuation=continuation_state,
        )
        run_id_str = str(run_id)
        emitter = RuntimeEventEmitter(stamper=envelope, run_id=run_id_str)
        orchestrator_id = planner_orchestrator_id(run_id_str)
        ctx.extra["runtime_logging_level"] = run_logging_level

        # Load planner role config for context snapshot
        role_service = SystemLLMRoleService(self._session)
        try:
            planner_role_config = await role_service.get_role_config(SystemLLMRoleType.PLANNER)
            planner_prompt = planner_role_config.get("prompt", "")
            planner_model = planner_role_config.get("model")
        except Exception:
            planner_prompt = ""
            planner_model = None

        budget_resolver = BudgetResolver(self._session)
        run_limits_v2 = await budget_resolver.resolve_run(platform.config, request.sandbox_overrides)
        planner_limits = await budget_resolver.resolve_orchestrator("planner", request.sandbox_overrides)

        run_context_snapshot = compact_snapshot(
            inputs={
                "user_request": request.request_text,
                "goal": effective_goal,
                "current_user_query": effective_user_query,
            },
            limits=serialize_limits(run_limits_v2.as_entity_limits()),
            meta={
                "agent_slug": effective_agent_slug or explicit_slug,
                "model": request.model,
                "continuation": continuation_state or None,
            },
        )
        planner_context_snapshot = compact_snapshot(
            inputs={
                "goal": effective_goal,
            },
            prompt=prompt_snapshot(planner_prompt, run_logging_level),
            limits=serialize_limits(planner_limits),
            rbac=planner_rbac_audit if isinstance(planner_rbac_audit, dict) else None,
            meta={
                "role": "planner",
                "model": planner_model or request.model,
                "explicit_agent_slug": explicit_slug,
                "continuation": continuation_state or None,
            },
        )

        if self._run_store is not None:
            try:
                await self._run_store.start_or_resume_run(
                    tenant_id=str(tenant_id),
                    agent_slug=request.agent_slug or "planner",
                    logging_level=run_logging_level,
                    user_id=str(user_id),
                    chat_id=str(chat_id) if chat_id else None,
                    context_snapshot=run_context_snapshot,
                    run_id_override=run_id,
                    resume_from_run_id=run_id if resumed_from_run_id else None,
                )
            except Exception as _e:  # noqa: BLE001
                logger.warning("Failed to create/resume top-level AgentRun: %s", _e)

        yield emitter.emit(
            RuntimeEvent.run_start(
                run_id=run_id_str,
                context_snapshot=run_context_snapshot,
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield emitter.emit(
            RuntimeEvent.orchestrator_start(
                orchestrator_id=orchestrator_id,
                run_id=run_id_str,
                role="planner",
                context_snapshot=planner_context_snapshot,
            ),
            phase=OrchestrationPhase.PLANNER,
        )
        question_answer_event = _build_question_answer_event(
            run_id=run_id_str,
            orchestrator_id=orchestrator_id,
            checkpoint=resume_checkpoint,
        )
        if question_answer_event is not None:
            yield emitter.emit(
                question_answer_event,
                phase=OrchestrationPhase.PLANNER,
            )

        # Per-entity budget registry
        budget_registry = BudgetRegistry(run_limits=run_limits_v2)
        budget_registry.register(
            entity_type="run",
            entity_id=run_id_str,
            parent_entity_id=None,
            limits=run_limits_v2.as_entity_limits(),
        )
        ctx.extra["runtime_budget_registry"] = budget_registry
        ctx.extra["runtime_budget_resolver"] = budget_resolver
        run_budget_payload = budget_registry.emit_snapshot(run_id_str, reason="init") or {}
        yield emitter.emit(
            RuntimeEvent.budget_snapshot(
                entity_type="run",
                entity_id=run_id_str,
                parent_entity_id=None,
                own=run_budget_payload.get("own", {}),
                limits=run_budget_payload.get("limits"),
                delta={},
                reason="init",
                at_ms=run_budget_payload.get("at_ms"),
            ),
            phase=OrchestrationPhase.PIPELINE,
        )

        # --- Planning (single decision engine) --------------------------
        planning_stage = self._assembler.build_planning_stage(
            max_iterations=platform.policy.max_steps,
        )
        async for phased in planning_stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform.config,
            orchestrator_id=orchestrator_id,
        ):
            yield emitter.emit_phased(phased)

        assert planning_stage.outcome is not None
        planning_outcome = planning_stage.outcome
        await_background_tail = bool(getattr(request, "await_background_tail", True))

        if planning_outcome.kind in (
            PlanningOutcomeKind.PAUSED,
            PlanningOutcomeKind.ABORTED,
            PlanningOutcomeKind.FAILED,
        ):
            terminal_status = (planning_outcome.stop_reason.value if planning_outcome.stop_reason else "failed")
            yield emitter.emit(
                RuntimeEvent.orchestrator_end(
                    orchestrator_id=orchestrator_id,
                    run_id=run_id_str,
                    status=terminal_status,
                ),
                phase=OrchestrationPhase.PLANNER,
            )
            # Mark status only (paused_action/context are stored by endpoint or
            # orchestrator before pipeline gets here, e.g., via turn_service.pause_turn
            # or SandboxService.pause_run). We only update status here.
            if planning_outcome.kind == PlanningOutcomeKind.PAUSED and self._run_store is not None:
                try:
                    pause_status = planning_outcome.stop_reason.value if planning_outcome.stop_reason else "paused"
                    await self._run_store.set_run_status(run_id=run_id, status=pause_status)
                except Exception as _e:  # noqa: BLE001
                    logger.warning("Failed to set paused status on AgentRun: %s", _e)
            elif self._run_store is not None:
                try:
                    await self._run_store.finish_run(
                        run_id=run_id,
                        status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "failed",
                    )
                except Exception as _e:  # noqa: BLE001
                    logger.warning("Failed to finish top-level AgentRun: %s", _e)
            if await_background_tail:
                # Sandbox/trace mode consumes the full runtime tail, including
                # memory writeback lifecycle.
                async for memory_ev in self._finalize_memory(
                    turn_mem=turn_mem,
                    runtime_state=runtime_state,
                    request=request,
                    stop_reason=planning_outcome.stop_reason,
                    emitter=emitter,
                    budget_resolver=budget_resolver,
                    logging_level=run_logging_level,
                ):
                    yield memory_ev
                yield emitter.emit(
                    RuntimeEvent.run_end(run_id=run_id_str, status=terminal_status),
                    phase=OrchestrationPhase.PIPELINE,
                )
            else:
                # Chat mode should stop streaming immediately after pause/error.
                await self._consume_memory_finalize_background(
                    turn_mem=turn_mem,
                    runtime_state=runtime_state,
                    request=request,
                    stop_reason=planning_outcome.stop_reason,
                    emitter=emitter,
                    budget_resolver=budget_resolver,
                    logging_level=run_logging_level,
                )
            return

        # --- Finalization -----------------------------------------------
        yield emitter.emit(
            RuntimeEvent.orchestrator_end(
                orchestrator_id=orchestrator_id,
                run_id=run_id_str,
                status="completed",
            ),
            phase=OrchestrationPhase.PLANNER,
        )

        if planning_outcome.kind == PlanningOutcomeKind.NEEDS_FINAL:
            async for ev in self._run_finalization(
                runtime_state=runtime_state,
                stop_reason=planning_outcome.stop_reason,
                planner_hint=planning_outcome.planner_hint,
                final_answer_strategy=planning_outcome.final_answer_strategy,
                model=request.model,
                platform_config=platform.config,
                sandbox_overrides=request.sandbox_overrides,
                envelope=envelope,
                run_id=run_id,
                budget_registry=budget_registry,
                budget_resolver=budget_resolver,
                logging_level=run_logging_level,
            ):
                yield ev
        # PlanningOutcomeKind.DIRECT already emitted delta+final inside
        # the stage; nothing to finalize beyond memory write-back below.

        if self._run_store is not None:
            try:
                await self._run_store.finish_run(
                    run_id=run_id,
                    status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "completed",
                )
            except Exception as _e:  # noqa: BLE001
                logger.warning("Failed to finish top-level AgentRun: %s", _e)

        if await_background_tail:
            # Sandbox/trace mode consumes the full runtime tail after final answer.
            async for memory_ev in self._finalize_memory(
                turn_mem=turn_mem,
                runtime_state=runtime_state,
                request=request,
                stop_reason=planning_outcome.stop_reason,
                emitter=emitter,
                budget_resolver=budget_resolver,
                logging_level=run_logging_level,
            ):
                yield memory_ev
            yield emitter.emit(
                RuntimeEvent.run_end(
                    run_id=run_id_str,
                    status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "completed",
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
        else:
            # Chat mode should finish the user stream on FINAL and dispatch memory
            # writeback in the background without surfacing tail events.
            await self._consume_memory_finalize_background(
                turn_mem=turn_mem,
                runtime_state=runtime_state,
                request=request,
                stop_reason=planning_outcome.stop_reason,
                emitter=emitter,
                budget_resolver=budget_resolver,
                logging_level=run_logging_level,
            )

    @staticmethod
    def _apply_sandbox_overrides(request: PipelineRequest, ctx: ToolContext) -> None:
        """Apply sandbox overrides from request into ToolContext as the canonical path."""
        request_overrides = dict(request.sandbox_overrides or {})
        budget_override = request_overrides.get("budget")
        if isinstance(budget_override, dict):
            canonical_budget: dict[str, int] = {}
            for src_key, dst_key in (
                ("planner_iterations", "max_planner_iterations"),
                ("max_planner_iterations", "max_planner_iterations"),
                ("agent_steps", "max_agent_steps"),
                ("max_agent_steps", "max_agent_steps"),
                ("tool_calls", "max_tool_calls_total"),
                ("max_tool_calls_total", "max_tool_calls_total"),
                ("retries", "max_retries"),
                ("max_retries", "max_retries"),
                ("wall_time_ms", "max_wall_time_ms"),
                ("max_wall_time_ms", "max_wall_time_ms"),
                ("tool_timeout_ms", "per_tool_timeout_ms"),
                ("per_tool_timeout_ms", "per_tool_timeout_ms"),
                ("max_steps_without_success", "max_steps_without_success"),
                ("loop_threshold", "loop_threshold"),
                ("max_tokens_total", "max_tokens_total"),
            ):
                value = budget_override.get(src_key)
                if isinstance(value, int):
                    canonical_budget[dst_key] = value
            if canonical_budget:
                runtime_budget = request_overrides.get("runtime_budget")
                merged_runtime_budget = dict(runtime_budget) if isinstance(runtime_budget, dict) else {}
                merged_runtime_budget.update(canonical_budget)
                request_overrides["runtime_budget"] = merged_runtime_budget
        if not request_overrides:
            return

        if hasattr(ctx, "get_runtime_deps") and hasattr(ctx, "set_runtime_deps"):
            deps = ctx.get_runtime_deps()
            merged: dict = {}
            if isinstance(getattr(deps, "sandbox_overrides", None), dict):
                merged.update(deps.sandbox_overrides)
            merged.update(request_overrides)
            deps.sandbox_overrides = merged
            ctx.set_runtime_deps(deps)
            return

        current = dict((getattr(ctx, "extra", {}) or {}).get("sandbox_overrides") or {})
        current.update(request_overrides)
        if not hasattr(ctx, "extra") or ctx.extra is None:
            ctx.extra = {}
        ctx.extra["sandbox_overrides"] = current

    @staticmethod
    async def _resolve_run_logging_level(ctx: ToolContext) -> str:
        """Resolve top-level run logging level with safe fallback."""
        if not isinstance(getattr(ctx, "extra", None), dict):
            return LoggingLevel.BRIEF.value
        try:
            return (await LoggingConfig.resolve(ctx)).value
        except Exception:
            return LoggingLevel.BRIEF.value

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _run_finalization(
        self,
        *,
        runtime_state: RuntimeTurnState,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"],
        model: Optional[str],
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        envelope: EventEnvelopeStamper,
        run_id: Optional[UUID] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        effective_run_id = run_id or runtime_state.run_id
        final_stage = self._assembler.build_finalization_stage()
        async for phased in final_stage.run(
            runtime_state=runtime_state,
            stop_reason=stop_reason,
            planner_hint=planner_hint,
            final_answer_strategy=final_answer_strategy,
            model=model,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
            budget_registry=budget_registry,
            budget_resolver=budget_resolver,
            run_synthesizer=True,
            logging_level=logging_level,
        ):
            ev = phased.event
            # Tag FINAL events with stop_reason so downstream can distinguish
            # a failed-but-synthesized turn from a genuinely completed one.
            if ev.type == RuntimeEventType.FINAL and stop_reason != PipelineStopReason.COMPLETED:
                ev = RuntimeEvent.final(
                    ev.data.get("content", ""),
                    sources=ev.data.get("sources"),
                    run_id=ev.data.get("run_id"),
                    stop_reason=stop_reason.value,
                )
                phased = PhasedEvent(ev, phased.phase)
            yield envelope.stamp_phased(phased, run_id=str(runtime_state.run_id))

    async def _finalize_memory(
        self,
        *,
        turn_mem: TurnMemory,
        runtime_state: RuntimeTurnState,
        request: PipelineRequest,
        stop_reason: PipelineStopReason,
        emitter: RuntimeEventEmitter,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Persist the turn's memory effects via MemoryWriter.

        Wraps every call in best-effort error handling: a write failure
        must never surface to the caller — the user already got their
        answer, we'd rather miss one turn of memory than double-fault.

        When RUNTIME_MEMORY_INLINE is False (default), the actual writeback
        is off-loaded to Celery for lower SSE latency.
        """
        # Sync agent_results from runtime_state to turn_mem
        turn_mem.agent_results = [
            AgentResultSnippet(
                agent=str(item.get("agent_slug") or item.get("agent") or ""),
                summary=str(item.get("summary") or ""),
                success=bool(item.get("success", True)),
            )
            for item in runtime_state.agent_results
        ]
        # Sync memory_bundle reference
        runtime_state.memory_bundle = turn_mem.memory_bundle
        assistant_final = runtime_state.final_answer or ""
        inline_memory = bool(RUNTIME_MEMORY_INLINE)
        if isinstance(request.sandbox_overrides, dict):
            inline_memory = inline_memory or bool(request.sandbox_overrides.get("memory_inline"))
        yield emitter.emit(
            RuntimeEvent.status(
                "memory_write_start",
                turn_number=turn_mem.turn_number,
                agent_results=len(turn_mem.agent_results or []),
                mode="inline" if inline_memory else "celery",
                parent_entity_type="orchestrator",
                parent_entity_id=_memory_orchestrator_id(str(runtime_state.run_id)),
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        if inline_memory:
            memory_orchestrator = _memory_orchestrator_id(str(runtime_state.run_id))
            component_ids = {
                "facts": f"{runtime_state.run_id}:memory:facts",
                "conversation": f"{runtime_state.run_id}:memory:conversation",
            }
            yield emitter.emit(
                RuntimeEvent.orchestrator_start(
                    orchestrator_id=memory_orchestrator,
                    run_id=str(runtime_state.run_id),
                    role="memory",
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            for component, component_id in component_ids.items():
                yield emitter.emit(
                    RuntimeEvent.agent_start(
                        agent_run_id=component_id,
                        parent_entity_type="orchestrator",
                        parent_entity_id=memory_orchestrator,
                        agent_slug=component,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
            memory_status = "completed"
            results: list[dict[str, Any]] = []
            failed_components: list[str] = []
            degraded_components: list[str] = []
            try:
                await self._assembler.memory_writer.finalize(
                    memory=turn_mem,
                    user_message=request.request_text,
                    assistant_final=assistant_final,
                    terminal_reason=stop_reason,
                    sandbox_overrides=request.sandbox_overrides,
                )
                diagnostics = turn_mem.memory_diagnostics or {}
                write_status = diagnostics.get("memory_write_status", {})
                results = [item for item in (write_status.get("results") or []) if isinstance(item, dict)]
                failed_components = [str(item) for item in (write_status.get("failed_components") or [])]
                degraded_components = [str(item) for item in (write_status.get("degraded_components") or [])]
                for index, item in enumerate(results, start=1):
                    component_name = str(item.get("component_name") or "unknown")
                    component_entity_id = component_ids.get(
                        component_name,
                        _memory_component_entity_id(str(runtime_state.run_id), component_name, index),
                    )
                    component_status = str(item.get("status") or "completed")
                    lifecycle_status = "failed" if component_status == "failed" else (
                        "paused" if component_status in {"degraded", "skipped"} else "completed"
                    )
                    yield emitter.emit(
                        RuntimeEvent.status(
                            "memory_component_result",
                            component_name=component_name,
                            status=component_status,
                            inserted_count=item.get("inserted_count", 0),
                            updated_count=item.get("updated_count", 0),
                            skipped_count=item.get("skipped_count", 0),
                            error_code=item.get("error_code"),
                            error_message=item.get("error_message"),
                            duration_ms=item.get("duration_ms", 0),
                            parent_entity_type="agent_run",
                            parent_entity_id=component_entity_id,
                        ),
                        phase=OrchestrationPhase.PIPELINE,
                    )
                    yield emitter.emit(
                        RuntimeEvent.agent_end(
                            agent_run_id=component_entity_id,
                            parent_entity_type="orchestrator",
                            parent_entity_id=memory_orchestrator,
                            agent_slug=component_name,
                            status=lifecycle_status,
                        ),
                        phase=OrchestrationPhase.PIPELINE,
                    )
            except Exception as exc:  # noqa: BLE001
                memory_status = "failed"
                memory_writer_finalize_failures_total.labels(
                    stop_reason=stop_reason.value if stop_reason else "unknown"
                ).inc()
                yield emitter.emit(
                    RuntimeEvent.status(
                        "memory_write_failed",
                        error=str(exc)[:500],
                        turn_number=turn_mem.turn_number,
                        parent_entity_type="orchestrator",
                        parent_entity_id=memory_orchestrator,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
            yield emitter.emit(
                RuntimeEvent.status(
                    "memory_write_end",
                    turn_number=turn_mem.turn_number,
                    failed_components=failed_components,
                    degraded_components=degraded_components,
                    parent_entity_type="orchestrator",
                    parent_entity_id=memory_orchestrator,
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            yield emitter.emit(
                RuntimeEvent.orchestrator_end(
                    orchestrator_id=memory_orchestrator,
                    run_id=str(runtime_state.run_id),
                    status=memory_status,
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            return

        try:
            tail_id = str(uuid4())
            stream_key: Optional[str] = None
            if isinstance(request.sandbox_overrides, dict):
                raw_stream_key = request.sandbox_overrides.get("sandbox_run_id")
                if isinstance(raw_stream_key, str) and raw_stream_key.strip():
                    stream_key = raw_stream_key.strip()
            if not stream_key:
                stream_key = str(runtime_state.run_id)

            from app.workers.tasks_memory import (
                finalize_memory_task,
                MemoryFinalizePayload,
                FactPayload,
                SummaryPayload,
                AgentResultPayload,
            )
            memory_limits: Optional[dict[str, int]] = None
            facts_limits: Optional[dict[str, int]] = None
            conversation_limits: Optional[dict[str, int]] = None
            try:
                if budget_resolver is not None:
                    memory_entity_limits = await budget_resolver.resolve_orchestrator("memory", request.sandbox_overrides)
                    facts_entity_limits = await budget_resolver.resolve_orchestrator("facts", request.sandbox_overrides)
                    conversation_entity_limits = await budget_resolver.resolve_orchestrator(
                        "conversation",
                        request.sandbox_overrides,
                    )

                    def _limits_payload(entity_limits) -> Optional[dict[str, int]]:
                        payload = {
                            "planner_steps": entity_limits.planner_steps,
                            "agent_steps": entity_limits.agent_steps,
                            "tool_calls": entity_limits.tool_calls,
                            "tokens_total": entity_limits.tokens_total,
                            "retries": entity_limits.retries,
                            "wall_time_ms": entity_limits.wall_time_ms,
                        }
                        values = {k: int(v) for k, v in payload.items() if isinstance(v, int) and v > 0}
                        return values or None

                    memory_limits = _limits_payload(memory_entity_limits)
                    facts_limits = _limits_payload(facts_entity_limits)
                    conversation_limits = _limits_payload(conversation_entity_limits)
            except Exception:
                logger.debug("Unable to resolve memory component limits", exc_info=True)
            # explicit limits are optional; worker handles missing values.
            payload = MemoryFinalizePayload(
                chat_id=str(turn_mem.chat_id) if turn_mem.chat_id else None,
                user_id=str(turn_mem.user_id) if turn_mem.user_id else None,
                tenant_id=str(turn_mem.tenant_id) if turn_mem.tenant_id else None,
                turn_number=turn_mem.turn_number,
                user_message=request.request_text,
                assistant_final=assistant_final,
                summary=SummaryPayload(
                    chat_id=str(turn_mem.summary.chat_id),
                    goals=list(turn_mem.summary.goals or []),
                    done=list(turn_mem.summary.done or []),
                    entities=dict(turn_mem.summary.entities or {}),
                    open_questions=list(turn_mem.summary.open_questions or []),
                    raw_tail=turn_mem.summary.raw_tail or "",
                    last_updated_turn=turn_mem.summary.last_updated_turn,
                ),
                retrieved_facts=[
                    FactPayload(
                        scope=f.scope.value,
                        subject=f.subject,
                        value=f.value,
                        source=f.source.value if f.source else "USER_UTTERANCE",
                        user_id=str(f.user_id) if f.user_id else None,
                        tenant_id=str(f.tenant_id) if f.tenant_id else None,
                        chat_id=str(f.chat_id) if f.chat_id else None,
                        confidence=f.confidence,
                    )
                    for f in (turn_mem.retrieved_facts or [])
                ],
                agent_results=[
                    AgentResultPayload(
                        agent=r.agent,
                        summary=r.summary,
                        success=r.success,
                    )
                    for r in turn_mem.agent_results
                ],
                skip_llm_helpers=False,
                terminal_reason=stop_reason.value if stop_reason else None,
                sandbox_overrides=request.sandbox_overrides,
                runtime_run_id=str(runtime_state.run_id),
                tail_id=tail_id,
                stream_key=stream_key,
                memory_limits=memory_limits,
                facts_limits=facts_limits,
                conversation_limits=conversation_limits,
                logging_level=logging_level,
            )
            finalize_memory_task.delay(payload.model_dump(mode="json"))
            yield emitter.emit(
                RuntimeEvent.status(
                    "memory_write_dispatched",
                    turn_number=turn_mem.turn_number,
                    mode="celery",
                    tail_id=tail_id,
                    stream_key=stream_key,
                    runtime_run_id=str(runtime_state.run_id),
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to dispatch memory task to Celery: %s", exc)
            memory_writer_finalize_failures_total.labels(
                stop_reason=stop_reason.value if stop_reason else "unknown"
            ).inc()
            yield emitter.emit(
                RuntimeEvent.status(
                    "memory_write_failed",
                    error=str(exc)[:500],
                    turn_number=turn_mem.turn_number,
                    parent_entity_type="orchestrator",
                    parent_entity_id=_memory_orchestrator_id(str(runtime_state.run_id)),
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            return

    async def _consume_memory_finalize_background(
        self,
        *,
        turn_mem: TurnMemory,
        runtime_state: RuntimeTurnState,
        request: PipelineRequest,
        stop_reason: PipelineStopReason,
        emitter: RuntimeEventEmitter,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
    ) -> None:
        """Run memory finalization side effects without surfacing tail events.

        Used by chat flows where the user stream must end on FINAL/STOP while
        memory extraction/compaction continues in the background.
        """
        async for _ in self._finalize_memory(
            turn_mem=turn_mem,
            runtime_state=runtime_state,
            request=request,
            stop_reason=stop_reason,
            emitter=emitter,
            budget_resolver=budget_resolver,
            logging_level=logging_level,
        ):
            pass

    async def _resolve_available_agents_for_planner(
        self,
        *,
        platform,
        explicit_slug: Optional[str],
        user_id: UUID,
        tenant_id: UUID,
    ) -> tuple[List[dict], dict]:
        """Build planner-visible agents with RBAC and explicit-slug validation.

        Why:
        - Platform snapshot provides routable agents globally.
        - Real availability is user/tenant-specific (RBAC + published version existence).
        - Without this filter planner can select an agent that preflight will reject.
        """
        candidates = platform.available_agents_for_planner(explicit_slug)

        # Validate explicit slug: keep pinning behavior, but only if there is
        # a published version for this tenant context.
        if explicit_slug:
            try:
                await AgentService(self._session).resolve_published_version(
                    agent_slug=explicit_slug,
                    tenant_id=tenant_id,
                )
            except Exception:
                logger.warning(
                    "Explicit agent slug '%s' is not runtime-resolvable",
                    explicit_slug,
                )
                from app.core.exceptions import AgentUnavailableError
                raise AgentUnavailableError(
                    f"Agent '{explicit_slug}' is not available or has no published version",
                    reason_code="agent_not_found",
                )

        default_collection_allow = bool(
            (platform.config or {}).get("default_collection_allow", True),
        )
        rbac = RuntimeRbacResolver(PermissionService(self._session))
        effective = await rbac.resolve_effective_permissions(
            user_id=user_id,
            tenant_id=tenant_id,
            default_collection_allow=default_collection_allow,
        )
        filtered, denied = rbac.filter_agents_by_slug(
            candidates,
            effective_permissions=effective,
            slug_getter=lambda item: str((item or {}).get("slug") or "").strip() or None,
            default_allow=True,
        )
        candidate_slugs = sorted({
            str((item or {}).get("slug") or "").strip()
            for item in candidates
            if str((item or {}).get("slug") or "").strip()
        })
        allowed_slugs = sorted({
            str((item or {}).get("slug") or "").strip()
            for item in filtered
            if str((item or {}).get("slug") or "").strip()
        })
        denied_slugs = sorted(set(denied))
        audit_payload = {
            "default_collection_allow": default_collection_allow,
            "candidates": candidate_slugs,
            "allowed": allowed_slugs,
            "denied_by_rbac": denied_slugs,
            "before_count": len(candidates),
            "after_count": len(filtered),
        }
        logger.info("Runtime RBAC planner agent filter: %s", audit_payload)
        return filtered, audit_payload


def _extract_attachment_ids(
    messages: Optional[List[dict]],
) -> tuple[List[str], int]:
    """Extract valid attachment IDs, returning (valid_ids, dropped_count).

    Logs warnings for dropped/invalid IDs to help diagnose frontend issues.
    """
    attachment_ids: List[str] = []
    dropped_count = 0
    for message in messages or []:
        meta = message.get("meta") if isinstance(message, dict) else None
        if not isinstance(meta, dict):
            continue
        raw_attachments = meta.get("attachments")
        if not isinstance(raw_attachments, list):
            continue
        for item in raw_attachments:
            if not isinstance(item, dict):
                dropped_count += 1
                logger.warning("Invalid attachment item (not dict): %s", item)
                continue
            raw_id = item.get("id")
            attachment_id = str(raw_id or "").strip()
            if not attachment_id or attachment_id == "None":
                dropped_count += 1
                logger.warning("Invalid/missing attachment id in item: %s", item)
                continue
            attachment_ids.append(attachment_id)
    return attachment_ids, dropped_count
