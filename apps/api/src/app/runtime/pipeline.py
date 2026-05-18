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
from app.agents.runtime.logging import LoggingConfig, LoggingLevel
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.budgets import BudgetExceededError, BudgetRegistry, BudgetResolver
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.event_emitter import RuntimeEventEmitter
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
        run_logging_level = await self._resolve_run_logging_level(ctx)
        if self._run_store is not None:
            try:
                await self._run_store.start_run(
                    tenant_id=str(tenant_id),
                    agent_slug=request.agent_slug or "planner",
                    logging_level=run_logging_level,
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
        run_id_str = str(run_id)
        emitter = RuntimeEventEmitter(stamper=envelope, run_id=run_id_str)
        orchestrator_id = f"{run_id}:orchestrator"
        yield emitter.emit(
            RuntimeEvent.run_start(run_id=run_id_str),
            phase=OrchestrationPhase.PIPELINE,
        )
        yield emitter.emit(
            RuntimeEvent.status(
                "planner_rbac_snapshot",
                rbac=planner_rbac_audit,
                explicit_agent_slug=explicit_slug,
            ),
            phase=OrchestrationPhase.PLANNER,
        )
        yield emitter.emit(
            RuntimeEvent.orchestrator_start(
                orchestrator_id=orchestrator_id,
                run_id=run_id_str,
                role="planner",
            ),
            phase=OrchestrationPhase.PLANNER,
        )

        # Per-entity budget registry
        budget_resolver = BudgetResolver(self._session)
        run_limits_v2 = await budget_resolver.resolve_run(platform.config)
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
            yield emitter.emit(
                RuntimeEvent.run_end(run_id=run_id_str, status=terminal_status),
                phase=OrchestrationPhase.PIPELINE,
            )
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
                model=request.model,
                envelope=envelope,
                run_id=run_id,
                budget_registry=budget_registry,
                budget_resolver=budget_resolver,
            ):
                yield ev
        # PlanningOutcomeKind.DIRECT already emitted delta+final inside
        # the stage; nothing to finalize beyond memory write-back below.

        yield emitter.emit(
            RuntimeEvent.run_end(
                run_id=run_id_str,
                status=planning_outcome.stop_reason.value if planning_outcome.stop_reason else "completed",
            ),
            phase=OrchestrationPhase.PIPELINE,
        )

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
        model: Optional[str],
        envelope: EventEnvelopeStamper,
        run_id: Optional[UUID] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        effective_run_id = run_id or runtime_state.run_id
        synthesis_id = f"{effective_run_id}:synthesis:1"
        if budget_registry is not None:
            synthesis_limits = None
            if budget_resolver is not None:
                try:
                    synthesis_limits = await budget_resolver.resolve_orchestrator("synthesizer")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to resolve synthesizer limits: %s", exc)
            budget_registry.register(
                entity_type="synthesis_run",
                entity_id=synthesis_id,
                parent_entity_id=str(effective_run_id),
                role="synthesizer",
                limits=synthesis_limits,
            )
            init_payload = budget_registry.emit_snapshot(synthesis_id, reason="init") or {}
            yield envelope.stamp(
                RuntimeEvent.budget_snapshot(
                    entity_type="synthesis_run",
                    entity_id=synthesis_id,
                    parent_entity_type="run",
                    parent_entity_id=str(effective_run_id),
                    role="synthesizer",
                    own=init_payload.get("own", {}),
                    limits=init_payload.get("limits"),
                    delta={},
                    reason="init",
                    at_ms=init_payload.get("at_ms"),
                ),
                OrchestrationPhase.SYNTHESIS,
                run_id=str(effective_run_id),
            )
        yield envelope.stamp(
            RuntimeEvent.synthesis_start(
                synthesis_id=synthesis_id,
                run_id=str(effective_run_id),
            ),
            OrchestrationPhase.SYNTHESIS,
            run_id=str(effective_run_id),
        )
        final_stage = self._assembler.build_finalization_stage()
        synthesis_status = "completed"
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
            if ev.type == RuntimeEventType.ERROR:
                synthesis_status = "failed"
            if budget_registry is not None:
                try:
                    if ev.type == RuntimeEventType.LLM_REQUEST:
                        in_tokens = self._estimate_tokens_from_payload(ev.data.get("messages"))
                        if in_tokens > 0:
                            budget_registry.consume(synthesis_id, "tokens_in", in_tokens, reason="tokens")
                            budget_registry.consume(synthesis_id, "tokens_total", in_tokens, reason="tokens")
                            snap = budget_registry.emit_snapshot(
                                synthesis_id,
                                reason="tokens",
                                delta={"tokens_in": in_tokens, "tokens_total": in_tokens},
                            ) or {}
                            yield envelope.stamp(
                                RuntimeEvent.budget_snapshot(
                                    entity_type="synthesis_run",
                                    entity_id=synthesis_id,
                                    parent_entity_type="run",
                                    parent_entity_id=str(effective_run_id),
                                    role="synthesizer",
                                    own=snap.get("own", {}),
                                    limits=snap.get("limits"),
                                    delta={"tokens_in": in_tokens, "tokens_total": in_tokens},
                                    reason="tokens",
                                    at_ms=snap.get("at_ms"),
                                ),
                                OrchestrationPhase.SYNTHESIS,
                                run_id=str(runtime_state.run_id),
                            )
                    elif ev.type == RuntimeEventType.LLM_RESPONSE:
                        out_tokens = self._estimate_tokens_from_payload(ev.data.get("content"))
                        if out_tokens > 0:
                            budget_registry.consume(synthesis_id, "tokens_out", out_tokens, reason="tokens")
                            budget_registry.consume(synthesis_id, "tokens_total", out_tokens, reason="tokens")
                            snap = budget_registry.emit_snapshot(
                                synthesis_id,
                                reason="tokens",
                                delta={"tokens_out": out_tokens, "tokens_total": out_tokens},
                            ) or {}
                            yield envelope.stamp(
                                RuntimeEvent.budget_snapshot(
                                    entity_type="synthesis_run",
                                    entity_id=synthesis_id,
                                    parent_entity_type="run",
                                    parent_entity_id=str(effective_run_id),
                                    role="synthesizer",
                                    own=snap.get("own", {}),
                                    limits=snap.get("limits"),
                                    delta={"tokens_out": out_tokens, "tokens_total": out_tokens},
                                    reason="tokens",
                                    at_ms=snap.get("at_ms"),
                                ),
                                OrchestrationPhase.SYNTHESIS,
                                run_id=str(runtime_state.run_id),
                            )
                    elif ev.type == RuntimeEventType.LLM_CALL:
                        dur = ev.data.get("duration_ms")
                        if isinstance(dur, int) and dur > 0:
                            budget_registry.consume(synthesis_id, "wall_time_ms", dur, reason="wall_time")
                            snap = budget_registry.emit_snapshot(
                                synthesis_id,
                                reason="wall_time",
                                delta={"wall_time_ms": dur},
                            ) or {}
                            yield envelope.stamp(
                                RuntimeEvent.budget_snapshot(
                                    entity_type="synthesis_run",
                                    entity_id=synthesis_id,
                                    parent_entity_type="run",
                                    parent_entity_id=str(effective_run_id),
                                    role="synthesizer",
                                    own=snap.get("own", {}),
                                    limits=snap.get("limits"),
                                    delta={"wall_time_ms": dur},
                                    reason="wall_time",
                                    at_ms=snap.get("at_ms"),
                                ),
                                OrchestrationPhase.SYNTHESIS,
                                run_id=str(runtime_state.run_id),
                            )
                except BudgetExceededError as exc:
                    synthesis_status = "failed"
                    yield envelope.stamp(
                        RuntimeEvent.error(
                            f"Synthesizer budget exceeded: {exc.metric}",
                            recoverable=False,
                            parent_entity_type="synthesis_run",
                            parent_entity_id=synthesis_id,
                        ),
                        OrchestrationPhase.SYNTHESIS,
                        run_id=str(runtime_state.run_id),
                    )
                    break
            yield envelope.stamp_phased(phased, run_id=str(runtime_state.run_id))
        if budget_registry is not None:
            final_payload = budget_registry.emit_snapshot(synthesis_id, reason="finalize") or {}
            yield envelope.stamp(
                RuntimeEvent.budget_snapshot(
                    entity_type="synthesis_run",
                    entity_id=synthesis_id,
                    parent_entity_type="run",
                    parent_entity_id=str(effective_run_id),
                    role="synthesizer",
                    own=final_payload.get("own", {}),
                    limits=final_payload.get("limits"),
                    delta={},
                    reason="finalize",
                    at_ms=final_payload.get("at_ms"),
                ),
                OrchestrationPhase.SYNTHESIS,
                run_id=str(effective_run_id),
            )
        yield envelope.stamp(
            RuntimeEvent.synthesis_end(
                synthesis_id=synthesis_id,
                run_id=str(effective_run_id),
                status=synthesis_status,
            ),
            OrchestrationPhase.SYNTHESIS,
            run_id=str(effective_run_id),
        )

    @staticmethod
    def _estimate_tokens_from_payload(value: object) -> int:
        import json

        if value is None:
            return 0
        try:
            if isinstance(value, str):
                raw = value
            else:
                raw = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            raw = str(value)
        raw = (raw or "").strip()
        if not raw:
            return 0
        return max(1, len(raw) // 4)

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
