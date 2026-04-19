"""
RuntimePipeline — thin coordinator.

Responsibilities (and NOTHING else):
    1. Resolve tenant/user/chat ids from the incoming request.
    2. Load the platform snapshot (config + routable agents + policy).
    3. Bootstrap WorkingMemory via ResumeResolver.
    4. Run stages in order (triage → planning → finalization) and route
       control based on their reported outcomes.
    5. Stamp the event envelope on every emitted event.

Construction of adapters/stages is delegated to `PipelineAssembler`.
Platform-level I/O (routable agents, policy limits, config) is delegated
to `PlatformConfigLoader`. Terminal persistence and rolling summary live
inside `FinalizationStage`.

All concrete adapter wiring lives in `app.runtime.assembler`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import EventEnvelopeStamper
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.platform_config import PlatformConfigLoader
from app.runtime.stages.planning_stage import PlanningOutcomeKind
from app.runtime.stages.triage_stage import TriageOutcomeKind
from app.services.run_store import RunStore

logger = get_logger(__name__)


class RuntimePipeline:
    """Coordinator. Stateless between turns; all turn state lives in
    WorkingMemory and in per-turn stage instances built by the assembler."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self._session = session
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
        chat_id: Optional[UUID] = UUID(request.chat_id) if request.chat_id else None
        user_id = UUID(request.user_id)
        tenant_id = UUID(request.tenant_id)

        envelope = EventEnvelopeStamper(chat_id=request.chat_id)
        platform = await PlatformConfigLoader(self._session).load()

        # --- Bootstrap ---------------------------------------------------
        bootstrap = await self._assembler.resume.bootstrap(
            request=request,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        memory = bootstrap.memory

        # --- Stage 1: Triage --------------------------------------------
        triage_stage = self._assembler.build_triage_stage()
        async for phased in triage_stage.run(
            memory=memory,
            latest_memory=bootstrap.latest,
            paused_runs=bootstrap.paused_runs,
            request=request,
            routable_agents=platform.routable_agents,
            platform_config=platform.config,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

        assert triage_stage.outcome is not None
        outcome = triage_stage.outcome
        memory = outcome.memory  # RESUMED may swap it

        if outcome.kind == TriageOutcomeKind.FINAL_ANSWERED:
            async for ev in self._run_finalization(
                memory=memory,
                stop_reason=PipelineStopReason.COMPLETED,
                planner_hint=None,
                model=request.model,
                run_synthesizer=False,
                envelope=envelope,
            ):
                yield ev
            yield envelope.stamp(
                RuntimeEvent.final(
                    memory.final_answer or "",
                    sources=[],
                    run_id=str(memory.run_id),
                ),
                OrchestrationPhase.TRIAGE,
                run_id=str(memory.run_id),
            )
            return

        if outcome.kind == TriageOutcomeKind.CLARIFY_PAUSED:
            return  # waiting_input + stop events already emitted

        # --- Stage 2: Planning ------------------------------------------
        explicit_slug = request.agent_slug or outcome.decision.agent_hint
        available_agents = platform.available_agents_for_planner(explicit_slug)
        if not available_agents:
            yield envelope.stamp(
                RuntimeEvent.error("No agents available for orchestration", recoverable=False),
                OrchestrationPhase.PREFLIGHT,
                run_id=str(memory.run_id),
            )
            await self._mark_failed(memory, "no_agents_available")
            return

        planning_stage = self._assembler.build_planning_stage(
            max_iterations=platform.policy.max_steps,
            max_wall_time_ms=platform.policy.max_wall_time_ms,
        )
        async for phased in planning_stage.run(
            memory=memory,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform.config,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

        assert planning_stage.outcome is not None
        planning_outcome = planning_stage.outcome

        if planning_outcome.kind in (
            PlanningOutcomeKind.PAUSED,
            PlanningOutcomeKind.ABORTED,
            PlanningOutcomeKind.FAILED,
        ):
            return  # terminal events already emitted, memory persisted inside stage

        # --- Stage 3: Finalization --------------------------------------
        async for ev in self._run_finalization(
            memory=memory,
            stop_reason=planning_outcome.stop_reason,
            planner_hint=planning_outcome.planner_hint,
            model=request.model,
            run_synthesizer=True,
            envelope=envelope,
        ):
            yield ev

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _run_finalization(
        self,
        *,
        memory,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
        run_synthesizer: bool,
        envelope: EventEnvelopeStamper,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        final_stage = self._assembler.build_finalization_stage()
        async for phased in final_stage.run(
            memory=memory,
            stop_reason=stop_reason,
            planner_hint=planner_hint,
            model=model,
            run_synthesizer=run_synthesizer,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

    async def _mark_failed(self, memory, reason: str) -> None:
        memory.status = PipelineStopReason.FAILED.value
        memory.final_error = reason
        memory.finished_at = datetime.now(timezone.utc)
        try:
            await self._assembler.memory.save(memory)
        except Exception as exc:
            logger.warning("Failed to persist failed memory: %s", exc)
