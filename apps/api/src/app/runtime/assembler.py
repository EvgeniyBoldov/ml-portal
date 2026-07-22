"""
PipelineAssembler — builds the per-turn collaborators used by RuntimePipeline.

The pipeline coordinator holds ONE assembler for its lifetime. Adapters
(Triage, Planner, AgentExecutor, Synthesizer, TurnSummarizer, MemoryPort,
ResumeResolver) are built lazily on first access and cached; stages are
constructed fresh per-turn because each stage carries mutable per-turn
`outcome` state.

This file is the single place where concrete adapters are wired to the
Protocols declared in `app.runtime.ports`. To swap an implementation for a
test or a new backend — override the corresponding `_build_*` method.
"""
from __future__ import annotations

from functools import cached_property
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.runtime.agent_executor import AgentExecutor
from app.runtime.memory.builder import MemoryBuilder
from app.runtime.memory.writer import MemoryWriter
from app.runtime.planner import Planner
from app.runtime.ports import (
    AgentExecutionPort,
    NextStepPlannerPort,
    SynthesizerPort,
)
from app.runtime.stages import FinalizationStage, PlanningStage
from app.runtime.synthesizer import Synthesizer
from app.runtime.orchestrator import DeterministicOrchestrator, SqlDeterministicOrchestrator
from app.runtime.plan_store import InMemoryPlanStore, SqlPlanStore
from app.runtime.planner.graph_planner import GraphPlanner
from app.runtime.planner.simple_planner import SimplePlanner
from app.runtime.stages.orchestrator_stage import OrchestratorStage
from app.services.runtime_observation_writer import RuntimeObservationWriter
from app.services.runtime_budget_service import RuntimeBudgetService


class PipelineAssembler:
    """Adapter and stage factory. One instance per RuntimePipeline."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._session = session
        self._llm_client = llm_client

    # ------------------------------------------------------------------ #
    # Adapters (cached for the pipeline's lifetime)                      #
    # ------------------------------------------------------------------ #

    @cached_property
    def memory_builder(self) -> MemoryBuilder:
        """Read path for cross-turn memory — facts + structured summary."""
        return MemoryBuilder(session=self._session)

    @cached_property
    def memory_writer(self) -> MemoryWriter:
        """Write path — extracts facts + compacts summary at turn end."""
        return MemoryWriter(
            session=self._session, llm_client=self._llm_client
        )

    @cached_property
    def planner(self) -> NextStepPlannerPort:
        return Planner(session=self._session, llm_client=self._llm_client)

    @cached_property
    def agent_executor(self) -> AgentExecutionPort:
        return AgentExecutor(
            session=self._session,
            llm_client=self._llm_client,
        )

    @cached_property
    def synthesizer(self) -> SynthesizerPort:
        return Synthesizer(session=self._session, llm_client=self._llm_client)

    # ------------------------------------------------------------------ #
    # Stage factories (fresh per turn)                                   #
    # ------------------------------------------------------------------ #

    def build_orchestrator_stage(self, *, task_executor: object) -> OrchestratorStage:
        return OrchestratorStage(
            orchestrator=DeterministicOrchestrator(
                store=InMemoryPlanStore(), planner=SimplePlanner(), executor=task_executor,
            )
        )

    def build_planning_stage(self, *, max_iterations: int) -> PlanningStage:
        return PlanningStage(
            planner=self.planner,
            agent_executor=self.agent_executor,
            max_iterations=max_iterations,
        )

    def build_sql_orchestrator_stage(self, *, task_executor: object) -> OrchestratorStage:
        observation_writer = RuntimeObservationWriter(self._session)
        return OrchestratorStage(
            orchestrator=SqlDeterministicOrchestrator(
                store=SqlPlanStore(self._session),
                planner=GraphPlanner(session=self._session, llm_client=self._llm_client),
                executor=task_executor,
                observation_writer=observation_writer,
                budget_service=RuntimeBudgetService(self._session, observation_writer),
            )
        )

    def build_finalization_stage(self) -> FinalizationStage:
        return FinalizationStage(synthesizer=self.synthesizer)
