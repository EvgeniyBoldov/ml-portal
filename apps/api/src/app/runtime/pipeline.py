"""
RuntimePipeline — thin coordinator (no triage).

Responsibilities (and NOTHING else):
    1. Resolve tenant/user/chat ids from the incoming request.
    2. Load the platform snapshot (config + routable agents + policy).
    3. Ask `MemoryBuilder` to assemble the turn's memory from the
       persisted FactStore.
    4. Initialize `RuntimeTurnState` as the single source of truth.
    5. Run the persisted graph planning stage until the plan pauses or reaches
       a terminal state.
    6. Run FinalizationStage for NEEDS_FINAL outcomes (synthesizer).
    7. Hand off to `MemoryWriter.finalize` to persist extracted facts.

Triage is gone. The planner absorbs clarify.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.contracts import ExecutionMode, PipelineRequest, PipelineStopReason
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot, serialize_limits
from app.runtime.envelope import PhasedEvent
from app.runtime.entity_ids import (
    interaction_id as _interaction_id,
    memory_component_entity_id as _memory_component_entity_id,
    memory_preparation_orchestrator_id as _memory_preparation_orchestrator_id,
    memory_orchestrator_id as _memory_orchestrator_id,
    planner_orchestrator_id,
)
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.memory.fact_extractor import AgentResultSnippet, FactEvidence
from app.runtime.memory.transport import TurnMemory
from app.runtime.platform_config import PlatformConfigLoader
from app.runtime.stages.graph_planning_stage import GraphPlanningOutcomeKind
from app.runtime.turn_state import RuntimeTurnState
from app.core.prometheus_metrics import memory_writer_finalize_failures_total
from app.models.system_llm_role import SystemLLMRoleType
from app.services.agent_service import AgentService
from app.services.permission_service import PermissionService
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.runtime_event_logger import RuntimeEventJournalFactory, RuntimeLogContext, RuntimeLoggingLevel
from app.services.glossary_service import GlossaryService

# Memory writeback runs via Celery (single canonical execution mode).
RUNTIME_MEMORY_INLINE = False
MEMORY_PREPARATION_PROJECT_LIMIT = 200

logger = get_logger(__name__)


def _tool_fact_evidence_text(value: Any, *, limit: int = 8_000) -> str:
    """Bound a direct successful tool result for asynchronous fact extraction."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value or "")
    return text[:limit]


def _tool_fact_evidence_support_ref(value: Any, *, fallback: str) -> str:
    """Return a stable retrieval-source identity for glossary confirmation."""
    if isinstance(value, dict):
        hits = value.get("hits")
        if isinstance(hits, list):
            refs = sorted({
                str(item.get("artifact_id") or item.get("id") or "").strip()
                for item in hits
                if isinstance(item, dict)
                and str(item.get("artifact_id") or item.get("id") or "").strip()
            })
            if refs:
                return "|".join(refs)[:128]
    return fallback[:128]


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


def _extract_execution_mode(request: PipelineRequest, checkpoint: Optional[Dict[str, Any]]) -> ExecutionMode:
    if isinstance(getattr(request, "execution_mode", None), ExecutionMode):
        return request.execution_mode
    requested = str(getattr(request, "execution_mode", "") or "").strip().lower()
    if requested == ExecutionMode.THINKING.value:
        return ExecutionMode.THINKING
    if requested == ExecutionMode.NORMAL.value:
        return ExecutionMode.NORMAL

    if isinstance(checkpoint, dict):
        source_snapshot = checkpoint.get("source_context_snapshot")
        if isinstance(source_snapshot, dict):
            meta = source_snapshot.get("meta")
            if isinstance(meta, dict):
                value = str(meta.get("execution_mode") or "").strip().lower()
                if value == ExecutionMode.THINKING.value:
                    return ExecutionMode.THINKING
        value = str(checkpoint.get("execution_mode") or "").strip().lower()
        if value == ExecutionMode.THINKING.value:
            return ExecutionMode.THINKING
    return ExecutionMode.NORMAL


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
        interaction_id=_interaction_id(str(run_id)),
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
    ) -> None:
        self._session = session
        self._assembler = PipelineAssembler(
            session=session, llm_client=llm_client,
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

        platform = await PlatformConfigLoader(self._session).load()
        resume_checkpoint = _extract_resume_checkpoint(request)
        effective_goal = _extract_effective_goal(request, resume_checkpoint)
        continuation_state = _build_continuation_state(request, resume_checkpoint)
        effective_user_query = _extract_effective_user_query(request, resume_checkpoint)
        execution_mode = _extract_execution_mode(request, resume_checkpoint)

        # --- RBAC resolve FIRST (before memory build) -----------------
        # If agent_slug is denied by RBAC, we treat it as None (fallback to default)
        explicit_slug = request.agent_slug
        available_agents, planner_rbac_audit = await self._resolve_available_agents_for_planner(
            platform=platform,
            explicit_slug=explicit_slug,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        # Sanitize against planner-visible slugs, not raw dict rows.
        available_agent_slugs = {
            str(item.get("slug") or "").strip()
            for item in available_agents
            if str(item.get("slug") or "").strip()
        }
        effective_agent_slug = explicit_slug if explicit_slug in available_agent_slugs else None

        # --- Memory: read path ----------------------------------------
        turn_mem = await self._assembler.memory_builder.build(
            goal=effective_goal,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            messages=list(request.messages or []),
            agent_slug=effective_agent_slug,  # RBAC-sanitized
            attachments=list(request.attachments or []),
            platform_config=platform.config,
            sandbox_overrides=request.sandbox_overrides,
        )

        # Initialize RuntimeTurnState as the single source of truth
        # For resume, use the original run_id; otherwise generate new
        resumed_from_run_id = continuation_state.get("resumed_from_run_id") if isinstance(continuation_state, dict) else None
        sandbox_run_id = (request.sandbox_overrides or {}).get("sandbox_run_id")
        if request.runtime_run_id:
            try:
                run_id = UUID(str(request.runtime_run_id))
            except (TypeError, ValueError):
                run_id = uuid4()
        elif sandbox_run_id:
            try:
                run_id = UUID(str(sandbox_run_id))
            except (TypeError, ValueError):
                run_id = uuid4()
        elif resumed_from_run_id:
            try:
                run_id = UUID(resumed_from_run_id)
            except ValueError:
                run_id = uuid4()
        else:
            run_id = uuid4()

        run_logging_level = (RuntimeLoggingLevel.FULL if bool((request.sandbox_overrides or {}).get("sandbox_run_id")) else RuntimeLoggingLevel.NONE).value

        runtime_state = RuntimeTurnState.from_seed(
            run_id=run_id,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            goal=effective_goal,
            current_user_query=effective_user_query,
            memory_bundle=turn_mem.memory_bundle,
            attachment_contexts=list(request.attachments or []),
            continuation=continuation_state,
        )
        runtime_state.execution_mode = execution_mode
        run_id_str = str(run_id)
        sandbox_run = bool((request.sandbox_overrides or {}).get("sandbox_run_id"))
        root_logger = RuntimeEventJournalFactory.create(
            context=RuntimeLogContext(
                run_id=run_id,
                level=RuntimeLoggingLevel.FULL if sandbox_run else RuntimeLoggingLevel.NONE,
                origin="sandbox" if sandbox_run else "chat",
                tenant_id=tenant_id,
                user_id=user_id,
                chat_id=chat_id,
                entity_type="run",
                entity_id=run_id_str,
                stream_logs=sandbox_run,
                stream_progress=True,
            ),
            session_factory=ctx.get_runtime_deps().session_factory,
        )
        ctx.extra["runtime_root_run_id"] = run_id_str
        ctx.extra["runtime_event_logger"] = root_logger
        emitter = root_logger
        orchestrator_id = planner_orchestrator_id(run_id_str)
        ctx.extra["runtime_logging_level"] = run_logging_level
        yield await emitter.emit(
            RuntimeEvent.status(
                "memory_snapshot_loaded",
                user_entries=len(turn_mem.durable_snapshot.user_facts),
                tenant_entries=len(turn_mem.durable_snapshot.tenant_facts),
                planner_entries=len(turn_mem.planner_memory_context),
                parent_entity_type="run",
                parent_entity_id=run_id_str,
            ),
            phase=OrchestrationPhase.PIPELINE,
        )

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
                "execution_mode": execution_mode.value,
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
                "execution_mode": execution_mode.value,
                "explicit_agent_slug": explicit_slug,
                "continuation": continuation_state or None,
            },
        )

        yield await emitter.emit(
            RuntimeEvent.run_start(
                run_id=run_id_str,
                context_snapshot=run_context_snapshot,
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        # --- Memory preparation (single LLM call, no tools) -----------
        memory_preparation_orchestrator = _memory_preparation_orchestrator_id(run_id_str)
        memory_preparation_executor = _memory_component_entity_id(
            run_id_str, "memory_preparation", 1,
        )
        project_glossary = await GlossaryService(self._session).list_project_terms(
            limit=MEMORY_PREPARATION_PROJECT_LIMIT,
        )
        global_glossary = await GlossaryService(self._session).list_confirmed_global_terms(
            limit=MEMORY_PREPARATION_PROJECT_LIMIT,
        )
        yield await emitter.emit(
            RuntimeEvent.orchestrator_start(
                orchestrator_id=memory_preparation_orchestrator,
                run_id=run_id_str,
                role="memory_preparation",
                context_snapshot=compact_snapshot(
                    inputs={"user_request": request.request_text},
                    meta={
                        "role": "memory_preparation",
                        "facts_available": len(turn_mem.durable_snapshot.entries),
                        "project_terms_available": len(project_glossary),
                        "global_glossary_available": len(global_glossary),
                    },
                ),
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield await emitter.emit(
            RuntimeEvent.agent_start(
                agent_execution_id=memory_preparation_executor,
                parent_entity_type="orchestrator",
                parent_entity_id=memory_preparation_orchestrator,
                agent_slug="memory_preparation",
                executor_type="orchestrator",
                executor_name="Подготовка памяти",
                task_title="Отбор контекста для планера",
            ),
            phase=OrchestrationPhase.PIPELINE,
        )

        async def _memory_preparation_event(event: RuntimeEvent) -> None:
            await emitter.emit(event, phase=OrchestrationPhase.PIPELINE)

        prepared_memory = await self._assembler.memory_preparer.prepare(
            request_text=request.request_text,
            facts=turn_mem.durable_snapshot.entries,
            project_glossary=project_glossary,
            glossary=global_glossary,
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            sandbox_overrides=request.sandbox_overrides,
            event_sink=_memory_preparation_event,
            agent_execution_id=memory_preparation_executor,
        )
        turn_mem.planner_memory_context = list(prepared_memory.items)
        yield await emitter.emit(
            RuntimeEvent.status(
                "memory_context_prepared",
                entity_type="agent_execution",
                entity_id=memory_preparation_executor,
                parent_entity_type="orchestrator",
                parent_entity_id=memory_preparation_orchestrator,
                selected_facts=prepared_memory.selected_fact_count,
                selected_projects=prepared_memory.selected_project_count,
                ambiguities=prepared_memory.ambiguities,
                fallback=prepared_memory.fallback,
                memory_context=prepared_memory.items,
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield await emitter.emit(
            RuntimeEvent.agent_end(
                agent_execution_id=memory_preparation_executor,
                parent_entity_type="orchestrator",
                parent_entity_id=memory_preparation_orchestrator,
                agent_slug="memory_preparation",
                status="completed",
                outcome="degraded" if prepared_memory.fallback else "completed",
                summary=f"Контекст: {len(prepared_memory.items)} элементов",
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield await emitter.emit(
            RuntimeEvent.orchestrator_end(
                orchestrator_id=memory_preparation_orchestrator,
                run_id=run_id_str,
                status="completed",
            ),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield await emitter.emit(
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
            yield await emitter.emit(
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
        yield await emitter.emit(
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
        planning_stage = self._assembler.build_graph_planning_stage(
            # One initial plan plus the configured number of replans. This is
            # a loop guard, not a graph-size/task-count limit.
            max_steps=run_limits_v2.plan_revisions or 1,
        )
        async for phased in planning_stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform.config,
            planner_rbac_audit=planner_rbac_audit,
            planner_memory_context=turn_mem.planner_memory_context,
            durable_memory_snapshot=turn_mem.durable_snapshot,
            orchestrator_id=orchestrator_id,
            runtime_limits=serialize_limits(run_limits_v2.as_entity_limits()),
        ):
            yield await emitter.emit(phased.event, phase=phased.phase)

        assert planning_stage.outcome is not None
        planning_outcome = planning_stage.outcome
        await_background_tail = bool(getattr(request, "await_background_tail", True))

        if planning_outcome.kind in (
            GraphPlanningOutcomeKind.PAUSED,
            GraphPlanningOutcomeKind.FAILED,
        ):
            terminal_status = (planning_outcome.stop_reason.value if planning_outcome.stop_reason else "failed")
            yield await emitter.emit(
                RuntimeEvent.orchestrator_end(
                    orchestrator_id=orchestrator_id,
                    run_id=run_id_str,
                    status=terminal_status,
                ),
                phase=OrchestrationPhase.PLANNER,
            )
            if planning_outcome.kind == GraphPlanningOutcomeKind.PAUSED:
                # A paused run must stop the user-visible stream immediately.
                # There is no synthesized response to persist yet.
                yield await emitter.emit(
                    RuntimeEvent.stop(
                        reason=terminal_status,
                        run_id=run_id_str,
                        question=planning_outcome.pause_question,
                        message=planning_outcome.pause_message,
                        action=(
                            {"kind": "confirm", **(planning_outcome.pause_context or {})}
                            if terminal_status == PipelineStopReason.WAITING_CONFIRMATION.value
                            else None
                        ),
                        context=planning_outcome.pause_context,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
            else:
                # A failed graph has no FINAL event. Emit an explicit safe
                # transport error so chat clients do not observe a silent EOF.
                yield await emitter.emit(
                    RuntimeEvent.error(
                        "Runtime execution failed",
                        recoverable=True,
                        error_code="runtime_execution_failed",
                        retryable=True,
                        user_message=(
                            "Во время выполнения запроса возникли временные проблемы. "
                            "Попробуйте повторить запрос позже."
                        ),
                        source="runtime",
                        parent_entity_type="run",
                        parent_entity_id=run_id_str,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
            if await_background_tail:
                yield await emitter.emit(
                    RuntimeEvent.run_end(run_id=run_id_str, status=terminal_status),
                    phase=OrchestrationPhase.PIPELINE,
                )
            return

        # --- Finalization -----------------------------------------------
        yield await emitter.emit(
            RuntimeEvent.orchestrator_end(
                orchestrator_id=orchestrator_id,
                run_id=run_id_str,
                status="completed",
            ),
            phase=OrchestrationPhase.PLANNER,
        )

        if planning_outcome.kind == GraphPlanningOutcomeKind.NEEDS_FINAL:
            async for ev in self._run_finalization(
                runtime_state=runtime_state,
                stop_reason=planning_outcome.stop_reason,
                answer_brief=planning_outcome.answer_brief,
                final_answer_strategy=planning_outcome.final_answer_strategy,
                model=request.model,
                platform_config=platform.config,
                sandbox_overrides=request.sandbox_overrides,
                emitter=emitter,
                run_id=run_id,
                budget_registry=budget_registry,
                budget_resolver=budget_resolver,
                logging_level=run_logging_level,
            ):
                yield ev
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
            yield await emitter.emit(
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
            yield await emitter.emit(
                RuntimeEvent.run_end(
                    run_id=run_id_str,
                    status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "completed",
                ),
                phase=OrchestrationPhase.PIPELINE,
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

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _run_finalization(
        self,
        *,
        runtime_state: RuntimeTurnState,
        stop_reason: PipelineStopReason,
        answer_brief: Optional[str],
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"],
        model: Optional[str],
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        emitter: RuntimeEventLogger,
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
            answer_brief=answer_brief,
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
                    attachments=ev.data.get("attachments"),
                    stop_reason=stop_reason.value,
                )
                phased = PhasedEvent(ev, phased.phase)
            yield await emitter.emit(phased.event, phase=phased.phase)

    async def _finalize_memory(
        self,
        *,
        turn_mem: TurnMemory,
        runtime_state: RuntimeTurnState,
        request: PipelineRequest,
        stop_reason: PipelineStopReason,
        emitter: RuntimeEventLogger,
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
                artifacts=list(item.get("artifacts") or []),
            )
            for item in runtime_state.agent_results
        ]
        turn_mem.artifacts = [
            item.model_dump(mode="json") for item in runtime_state.attachment_contexts
        ] + [
            artifact
            for item in runtime_state.agent_results
            for artifact in (item.get("artifacts") or [])
            if isinstance(artifact, dict)
        ]
        turn_mem.fact_run_ref = str(runtime_state.run_id)
        turn_mem.fact_evidence = [
            FactEvidence(
                source_id=str(entry.call_id),
                source_type="tool_result",
                source_ref=str(entry.call_id),
                text=_tool_fact_evidence_text(entry.result_data),
                label=str(entry.operation),
                support_ref=_tool_fact_evidence_support_ref(
                    entry.result_data,
                    fallback=str(entry.call_id),
                ),
            )
            for entry in runtime_state.tool_ledger.entries
            if entry.status == "succeeded" and entry.result_data is not None
        ]
        turn_mem.project_memory_candidates = list(runtime_state.project_memory_candidates)
        # Sync memory_bundle reference
        runtime_state.memory_bundle = turn_mem.memory_bundle
        assistant_final = runtime_state.final_answer or ""
        inline_memory = bool(RUNTIME_MEMORY_INLINE)
        if isinstance(request.sandbox_overrides, dict):
            inline_memory = inline_memory or bool(request.sandbox_overrides.get("memory_inline"))
        yield await emitter.emit(
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
                "fact_extractor": _memory_component_entity_id(str(runtime_state.run_id), "fact_extractor", 1),
                "fact_compactor": _memory_component_entity_id(str(runtime_state.run_id), "fact_compactor", 2),
            }
            yield await emitter.emit(
                RuntimeEvent.orchestrator_start(
                    orchestrator_id=memory_orchestrator,
                    run_id=str(runtime_state.run_id),
                    role="memory",
                ),
                phase=OrchestrationPhase.PIPELINE,
            )
            for component, component_id in component_ids.items():
                yield await emitter.emit(
                    RuntimeEvent.agent_start(
                        agent_execution_id=component_id,
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
                async def _memory_llm_event(event: RuntimeEvent) -> None:
                    await emitter.emit(event, phase=OrchestrationPhase.PIPELINE)

                writer = self._assembler.build_memory_writer(
                    llm_event_sink=lambda _component, event: _memory_llm_event(event),
                    component_execution_ids=component_ids,
                )
                await writer.finalize(
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
                    # Memory degradation/skipping is a completed best-effort
                    # post-response component, not a user-interaction pause.
                    lifecycle_status = "failed" if component_status == "failed" else "completed"
                    yield await emitter.emit(
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
                            facts=item.get("facts", []),
                            entity_type="agent_execution",
                            entity_id=component_entity_id,
                            parent_entity_type="orchestrator",
                            parent_entity_id=memory_orchestrator,
                        ),
                        phase=OrchestrationPhase.PIPELINE,
                    )
                    yield await emitter.emit(
                        RuntimeEvent.agent_end(
                            agent_execution_id=component_entity_id,
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
                yield await emitter.emit(
                    RuntimeEvent.status(
                        "memory_write_failed",
                        error=str(exc)[:500],
                        turn_number=turn_mem.turn_number,
                        parent_entity_type="orchestrator",
                        parent_entity_id=memory_orchestrator,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
            yield await emitter.emit(
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
            yield await emitter.emit(
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
                FactEvidencePayload,
                ProjectMemoryCandidatePayload,
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
                            "plan_revisions": getattr(entity_limits, "plan_revisions", None),
                            "task_attempts": getattr(entity_limits, "task_attempts", None),
                            "agent_runs": getattr(entity_limits, "agent_runs", None),
                            "llm_calls": getattr(entity_limits, "llm_calls", None),
                            "tool_calls": getattr(entity_limits, "tool_calls", None),
                            "tokens_total": getattr(entity_limits, "tokens_total", None),
                            "retries": getattr(entity_limits, "retries", None),
                            "wall_time_ms": getattr(entity_limits, "wall_time_ms", None),
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
                        tenant_id=str(f.tenant_id) if f.tenant_id else None,
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
                fact_evidence=[FactEvidencePayload(**item.model_dump()) for item in turn_mem.fact_evidence],
                project_memory_candidates=[
                    ProjectMemoryCandidatePayload(**item.model_dump())
                    for item in turn_mem.project_memory_candidates
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
                runtime_log_context=(
                    emitter.worker_payload()
                    if getattr(emitter, "context", None) is not None
                    else None
                ),
            )
            finalize_memory_task.delay(payload.model_dump(mode="json"))
            yield await emitter.emit(
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
            yield await emitter.emit(
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
        emitter: RuntimeEventLogger,
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
            default_allow=False,
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
