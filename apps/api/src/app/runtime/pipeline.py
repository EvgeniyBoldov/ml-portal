"""
RuntimePipeline — thin coordinator.

Owns only:
    * Stage wiring (triage → planning → finalization)
    * Envelope stamping on every emitted event
    * High-level control flow based on stage outcomes
    * Platform config / routable-agents lookup (read-only snapshots)

Everything else — persistence, resume/paused state, synthesizer, rolling
summary, planner loop, agent execution — lives behind the stages and ports
in this package. Each concern has exactly one home.

Flow:
    bootstrap → triage → (direct answer → finalize-no-synth)
                      → (clarify → done)
                      → (proceed/resume → planning → finalize)
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.agent_executor import AgentExecutor
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import EventEnvelopeStamper, PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.memory import WorkingMemoryRepository
from app.runtime.planner import Planner
from app.runtime.ports import MemoryPort
from app.runtime.resume import ResumeResolver
from app.runtime.stages import (
    FinalizationStage,
    PlanningStage,
    TriageStage,
)
from app.runtime.stages.planning_stage import PlanningOutcomeKind
from app.runtime.stages.triage_stage import TriageOutcomeKind
from app.runtime.summarizer_turn import TurnSummarizer
from app.runtime.synthesizer import Synthesizer
from app.runtime.triage import Triage
from app.services.run_store import RunStore
from app.services.runtime_config_service import RuntimeConfigService

logger = get_logger(__name__)


MAX_PLANNER_ITERATIONS_DEFAULT = 12
MAX_WALL_TIME_MS_DEFAULT = 120_000


class RuntimePipeline:
    """Stage coordinator. Stateless between turns; all turn state lives in
    WorkingMemory and in per-turn envelope/stages built inside `execute()`.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self._session = session
        self._llm_client = llm_client
        self._run_store = run_store

        # Adapters (= port implementations). Constructed once per pipeline;
        # each carries only the session/llm_client it needs.
        self._memory: MemoryPort = WorkingMemoryRepository(session)
        self._triage = Triage(session=session, llm_client=llm_client)
        self._planner = Planner(session=session, llm_client=llm_client)
        self._agent_executor = AgentExecutor(
            session=session, llm_client=llm_client, run_store=run_store,
        )
        self._synthesizer = Synthesizer(session=session, llm_client=llm_client)
        self._summary = TurnSummarizer(session=session, llm_client=llm_client)
        self._resume = ResumeResolver(self._memory)
        self._config = RuntimeConfigService(session)

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
        platform_config = await self._load_platform_config()

        # --- Bootstrap: fresh WorkingMemory seeded from latest turn.
        bootstrap = await self._resume.bootstrap(
            request=request,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        memory = bootstrap.memory

        # --- Stage 1: Triage ---------------------------------------------
        triage_stage = TriageStage(
            triage=self._triage,
            memory_port=self._memory,
            resume=self._resume,
        )
        routable_agents = await self._list_routable_agents()
        async for phased in triage_stage.run(
            memory=memory,
            latest_memory=bootstrap.latest,
            paused_runs=bootstrap.paused_runs,
            request=request,
            routable_agents=routable_agents,
            platform_config=platform_config,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

        assert triage_stage.outcome is not None
        outcome = triage_stage.outcome
        memory = outcome.memory  # RESUMED may swap it

        # --- Terminal branches handled entirely by triage ----------------
        if outcome.kind == TriageOutcomeKind.FINAL_ANSWERED:
            # Direct-answer path: no synthesizer, but still roll the summary.
            final_stage = self._build_finalization_stage()
            async for phased in final_stage.run(
                memory=memory,
                stop_reason=PipelineStopReason.COMPLETED,
                planner_hint=None,
                model=request.model,
                run_synthesizer=False,
            ):
                yield envelope.stamp_phased(phased, run_id=str(memory.run_id))
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
            return  # stop events already emitted by TriageStage

        # --- Stage 2: Planning -------------------------------------------
        available_agents = self._available_agents_for_planner(
            routable_agents, request.agent_slug or outcome.decision.agent_hint,
        )
        if not available_agents:
            yield envelope.stamp(
                RuntimeEvent.error("No agents available for orchestration", recoverable=False),
                OrchestrationPhase.PREFLIGHT,
                run_id=str(memory.run_id),
            )
            await self._mark_failed(memory, "no_agents_available")
            return

        policy = self._derive_policy_limits(platform_config)
        planning_stage = PlanningStage(
            planner=self._planner,
            agent_executor=self._agent_executor,
            memory_port=self._memory,
            max_iterations=policy["max_steps"],
            max_wall_time_ms=policy["max_wall_time_ms"],
        )

        async for phased in planning_stage.run(
            memory=memory,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform_config,
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

        # --- Stage 3: Finalization ---------------------------------------
        final_stage = self._build_finalization_stage()
        async for phased in final_stage.run(
            memory=memory,
            stop_reason=planning_outcome.stop_reason,
            planner_hint=planning_outcome.planner_hint,
            model=request.model,
            run_synthesizer=True,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

    # ------------------------------------------------------------------ #
    # Builders / helpers                                                 #
    # ------------------------------------------------------------------ #

    def _build_finalization_stage(self) -> FinalizationStage:
        return FinalizationStage(
            synthesizer=self._synthesizer,
            summary=self._summary,
            memory_port=self._memory,
        )

    async def _mark_failed(self, memory, reason: str) -> None:
        from datetime import datetime, timezone
        memory.status = PipelineStopReason.FAILED.value
        memory.final_error = reason
        memory.finished_at = datetime.now(timezone.utc)
        try:
            await self._memory.save(memory)
        except Exception as exc:
            logger.warning("Failed to persist failed memory: %s", exc)

    async def _load_platform_config(self) -> Dict[str, Any]:
        try:
            return await self._config.get_pipeline_config()
        except Exception as exc:
            logger.warning("Failed to load platform config, using empty: %s", exc)
            return {}

    async def _list_routable_agents(self) -> List[Dict[str, Any]]:
        from app.services.agent_service import AgentService

        try:
            svc = AgentService(self._session)
            agents = await svc.list_routable_agents()
            return [
                {
                    "slug": getattr(a, "slug", None),
                    "description": getattr(a, "description", "") or "",
                }
                for a in agents
                if getattr(a, "slug", None)
            ]
        except Exception as exc:
            logger.warning("Failed to list routable agents: %s", exc)
            return []

    @staticmethod
    def _available_agents_for_planner(
        routable_agents: List[Dict[str, Any]],
        explicit_slug: Optional[str],
    ) -> List[Dict[str, Any]]:
        if explicit_slug:
            return [{"slug": explicit_slug, "description": ""}]
        return routable_agents

    @staticmethod
    def _derive_policy_limits(platform_config: Dict[str, Any]) -> Dict[str, int]:
        policy = platform_config.get("policy") if isinstance(platform_config, dict) else None
        policy = policy or {}
        return {
            "max_steps": int(policy.get("max_steps") or MAX_PLANNER_ITERATIONS_DEFAULT),
            "max_wall_time_ms": int(policy.get("max_wall_time_ms") or MAX_WALL_TIME_MS_DEFAULT),
        }
