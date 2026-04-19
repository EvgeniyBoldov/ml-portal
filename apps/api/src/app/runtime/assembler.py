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
from app.runtime.memory import WorkingMemoryRepository
from app.runtime.memory.builder import MemoryBuilder
from app.runtime.memory.writer import MemoryWriter
from app.runtime.planner import Planner
from app.runtime.ports import (
    AgentExecutionPort,
    MemoryPort,
    PlannerServicePort,
    SynthesizerPort,
)
from app.runtime.stages import (
    FinalizationStage,
    PlanningStage,
)
from app.runtime.synthesizer import Synthesizer
from app.services.run_store import RunStore


class PipelineAssembler:
    """Adapter and stage factory. One instance per RuntimePipeline."""

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

    # ------------------------------------------------------------------ #
    # Adapters (cached for the pipeline's lifetime)                      #
    # ------------------------------------------------------------------ #

    @cached_property
    def memory(self) -> MemoryPort:
        """Legacy WorkingMemory persistence (`execution_memories` table).

        Still used until the legacy WorkingMemory class is retired in M6 —
        the planner / synthesizer mutate a WorkingMemory per turn and the
        pipeline needs somewhere to persist intermediate state so paused
        runs can resume. New FactStore/SummaryStore handle cross-turn
        memory independently.
        """
        return WorkingMemoryRepository(self._session)

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
    def planner(self) -> PlannerServicePort:
        return Planner(session=self._session, llm_client=self._llm_client)

    @cached_property
    def agent_executor(self) -> AgentExecutionPort:
        return AgentExecutor(
            session=self._session,
            llm_client=self._llm_client,
            run_store=self._run_store,
        )

    @cached_property
    def synthesizer(self) -> SynthesizerPort:
        return Synthesizer(session=self._session, llm_client=self._llm_client)

    # ------------------------------------------------------------------ #
    # Stage factories (fresh per turn)                                   #
    # ------------------------------------------------------------------ #

    def build_planning_stage(
        self,
        *,
        max_iterations: int,
        max_wall_time_ms: int,
    ) -> PlanningStage:
        return PlanningStage(
            planner=self.planner,
            agent_executor=self.agent_executor,
            memory_port=self.memory,
            max_iterations=max_iterations,
            max_wall_time_ms=max_wall_time_ms,
        )

    def build_finalization_stage(self) -> FinalizationStage:
        return FinalizationStage(
            synthesizer=self.synthesizer,
            memory_port=self.memory,
        )
