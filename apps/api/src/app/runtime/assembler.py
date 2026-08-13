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
from app.runtime.memory.preparer import MemoryPreparer
from app.runtime.planner.graph_planner import GraphPlanner
from app.runtime.ports import SynthesizerPort, TaskExecutionPort
from app.runtime.stages import FinalizationStage
from app.runtime.synthesizer import Synthesizer
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import SqlPlanStore
from app.runtime.stages.graph_planning_stage import GraphPlanningStage
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
    def memory_preparer(self) -> MemoryPreparer:
        return MemoryPreparer(session=self._session, llm_client=self._llm_client)

    @cached_property
    def graph_planner(self) -> GraphPlanner:
        return GraphPlanner(session=self._session, llm_client=self._llm_client)

    @cached_property
    def agent_executor(self) -> TaskExecutionPort:
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

    def build_graph_planning_stage(self, *, max_steps: int) -> GraphPlanningStage:
        store = SqlPlanStore(self._session)
        return GraphPlanningStage(
            store=store,
            orchestrator=GraphOrchestrator(
                store=store,
                planner=self.graph_planner,
                executor=self.agent_executor,
                budget_service=RuntimeBudgetService(self._session),
            ),
            max_steps=max_steps,
        )

    def build_finalization_stage(self) -> FinalizationStage:
        return FinalizationStage(synthesizer=self.synthesizer)
