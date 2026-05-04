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

from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.budget import RuntimeBudget, RuntimeBudgetTracker
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.memory.fact_extractor import AgentResultSnippet
from app.runtime.memory.transport import TurnMemory
from app.runtime.platform_config import PlatformConfigLoader
from app.runtime.stages.planning_stage import PlanningOutcomeKind
from app.runtime.turn_state import RuntimeTurnState
from app.core.prometheus_metrics import memory_writer_finalize_failures_total
from app.services.agent_service import AgentService
from app.services.permission_service import PermissionService
from app.services.run_store import RunStore

logger = get_logger(__name__)


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

        # --- RBAC resolve FIRST (before memory build) -----------------
        # If agent_slug is denied by RBAC, we treat it as None (fallback to default)
        explicit_slug = request.agent_slug
        available_agents = await self._resolve_available_agents_for_planner(
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
            goal=request.request_text,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            messages=list(request.messages or []),
            agent_slug=effective_agent_slug,  # RBAC-sanitized
            attachment_ids=attachment_ids,
            platform_config=platform.config,
        )
        if attachments_dropped:
            turn_mem.memory_diagnostics = dict(turn_mem.memory_diagnostics or {})
            turn_mem.memory_diagnostics["attachments_dropped_count"] = attachments_dropped

        # Initialize RuntimeTurnState as the single source of truth
        run_id = uuid4()

        # --- Create top-level AgentRun so pause/resume can find it by run_id
        if self._run_store is not None:
            try:
                await self._run_store.start_run(
                    tenant_id=str(tenant_id),
                    agent_slug=request.agent_slug or "planner",
                    logging_level="brief",
                    user_id=str(user_id),
                    chat_id=str(chat_id) if chat_id else None,
                    run_id_override=run_id,
                )
            except Exception as _e:  # noqa: BLE001
                logger.warning("Failed to create top-level AgentRun: %s", _e)

        runtime_state = RuntimeTurnState.from_seed(
            run_id=run_id,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            goal=request.request_text,
            current_user_query=request.request_text,
            memory_bundle=turn_mem.memory_bundle,
        )

        # --- Planning (single decision engine) --------------------------
        runtime_budget = RuntimeBudget.from_platform_config(
            planner_max_steps=platform.policy.max_steps,
            planner_max_wall_time_ms=platform.policy.max_wall_time_ms,
            platform_config=platform.config,
        )
        budget_tracker = RuntimeBudgetTracker(budget=runtime_budget)
        ctx.extra["runtime_budget_tracker"] = budget_tracker

        planning_stage = self._assembler.build_planning_stage(
            max_iterations=platform.policy.max_steps,
            budget_tracker=budget_tracker,
        )
        async for phased in planning_stage.run(
            runtime_state=runtime_state,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform.config,
        ):
            yield envelope.stamp_phased(phased, run_id=str(runtime_state.run_id))

        assert planning_stage.outcome is not None
        planning_outcome = planning_stage.outcome

        if planning_outcome.kind in (
            PlanningOutcomeKind.PAUSED,
            PlanningOutcomeKind.ABORTED,
            PlanningOutcomeKind.FAILED,
        ):
            # Persist pause state so resume endpoint can find run by run_id.
            if planning_outcome.kind == PlanningOutcomeKind.PAUSED and self._run_store is not None:
                try:
                    pause_status = planning_outcome.stop_reason.value if planning_outcome.stop_reason else "paused"
                    # paused_action/context are stored by ChatTurnOrchestrator via
                    # turn_service.pause_turn; here we only mark the AgentRun as paused
                    # so the resume endpoint can look it up by run_id.
                    await self._run_store.pause_run(
                        run_id=run_id,
                        status=pause_status,
                        paused_action={},
                        paused_context={},
                    )
                except Exception as _e:  # noqa: BLE001
                    logger.warning("Failed to pause top-level AgentRun: %s", _e)
            elif self._run_store is not None:
                try:
                    await self._run_store.finish_run(
                        run_id=run_id,
                        status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "failed",
                    )
                except Exception as _e:  # noqa: BLE001
                    logger.warning("Failed to finish top-level AgentRun: %s", _e)
            # Memory write-back still runs for paused/aborted turns so
            # next turn sees the open_questions / error context.
            await self._finalize_memory(
                turn_mem=turn_mem,
                runtime_state=runtime_state,
                request=request,
                stop_reason=planning_outcome.stop_reason,
            )
            return

        # --- Finalization -----------------------------------------------
        if planning_outcome.kind == PlanningOutcomeKind.NEEDS_FINAL:
            async for ev in self._run_finalization(
                runtime_state=runtime_state,
                stop_reason=planning_outcome.stop_reason,
                planner_hint=planning_outcome.planner_hint,
                model=request.model,
                envelope=envelope,
            ):
                yield ev
        # PlanningOutcomeKind.DIRECT already emitted delta+final inside
        # the stage; nothing to finalize beyond memory write-back below.

        # --- Memory: write path (new) -----------------------------------
        await self._finalize_memory(
            turn_mem=turn_mem,
            runtime_state=runtime_state,
            request=request,
            stop_reason=planning_outcome.stop_reason,
        )

    @staticmethod
    def _apply_sandbox_overrides(request: PipelineRequest, ctx: ToolContext) -> None:
        """Apply sandbox overrides from request into ToolContext as the canonical path."""
        request_overrides = dict(request.sandbox_overrides or {})
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
        planner_hint: Optional[str],
        model: Optional[str],
        envelope: EventEnvelopeStamper,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        final_stage = self._assembler.build_finalization_stage()
        async for phased in final_stage.run(
            runtime_state=runtime_state,
            stop_reason=stop_reason,
            planner_hint=planner_hint,
            model=model,
            run_synthesizer=True,
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
    ) -> None:
        """Persist the turn's memory effects via MemoryWriter.

        Wraps every call in best-effort error handling: a write failure
        must never surface to the caller — the user already got their
        answer, we'd rather miss one turn of memory than double-fault.
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
        try:
            await self._assembler.memory_writer.finalize(
                memory=turn_mem,
                user_message=request.request_text,
                assistant_final=assistant_final,
                terminal_reason=stop_reason,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MemoryWriter.finalize best-effort failed: %s", exc)
            memory_writer_finalize_failures_total.labels(
                stop_reason=stop_reason.value if stop_reason else "unknown"
            ).inc()

    async def _resolve_available_agents_for_planner(
        self,
        *,
        platform,
        explicit_slug: Optional[str],
        user_id: UUID,
        tenant_id: UUID,
    ) -> List[dict]:
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
        if denied:
            logger.info("Planner candidate agents denied by RBAC: %s", ", ".join(sorted(denied)))
        return filtered


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
