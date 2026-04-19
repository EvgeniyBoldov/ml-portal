"""
Runtime ports — Protocols that describe the boundaries of the pipeline.

The pipeline (and its stages) depend on these abstractions, not on concrete
adapters. Concrete adapters live next to them:

    MemoryPort              ← app.runtime.memory.repository.WorkingMemoryRepository
    SummaryPort             ← app.runtime.summarizer_turn.TurnSummarizer
    AgentExecutionPort      ← app.runtime.agent_executor.AgentExecutor
    SynthesizerPort         ← app.runtime.synthesizer.Synthesizer
    TriageServicePort       ← app.runtime.triage.triage.Triage
    PlannerServicePort      ← app.runtime.planner.planner.Planner

Keeping these as Protocols (structural typing) means we do not force existing
adapters to inherit — they already match by method shape.
"""
from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)
from uuid import UUID

from app.agents.context import ToolContext
from app.runtime.contracts import NextStep, TriageDecision
from app.runtime.events import RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory


# --------------------------------------------------------------------------- #
# Persistence                                                                  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class MemoryPort(Protocol):
    """Persistence adapter for WorkingMemory. The runtime only speaks the
    domain model — storage details (JSONB, columns, FKs) are hidden."""

    async def save(self, memory: WorkingMemory) -> None: ...

    async def load(self, run_id: UUID) -> Optional[WorkingMemory]: ...

    async def load_latest_for_chat(self, chat_id: UUID) -> Optional[WorkingMemory]: ...

    async def load_paused_for_chat(self, chat_id: UUID) -> List[WorkingMemory]: ...


# --------------------------------------------------------------------------- #
# Rolling summary                                                              #
# --------------------------------------------------------------------------- #


@runtime_checkable
class SummaryPort(Protocol):
    """Produces & persists a rolling dialogue summary at turn end."""

    async def run(
        self,
        *,
        memory: WorkingMemory,
        user_message: str,
        assistant_answer: str,
        recent_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]: ...


# --------------------------------------------------------------------------- #
# Triage / Planner                                                             #
# --------------------------------------------------------------------------- #


@runtime_checkable
class TriageServicePort(Protocol):
    """Stateless classifier — decides final / clarify / orchestrate / resume."""

    async def decide(
        self,
        *,
        request_text: str,
        memory: WorkingMemory,
        routable_agents: List[Dict[str, Any]],
        paused_runs: List[WorkingMemory],
        platform_config: Dict[str, Any],
        chat_id: Optional[UUID],
        tenant_id: UUID,
        user_id: UUID,
    ) -> TriageDecision: ...


@runtime_checkable
class PlannerServicePort(Protocol):
    """Next-step planner — produces one NextStep per invocation."""

    async def next_step(
        self,
        *,
        memory: WorkingMemory,
        available_agents: List[Dict[str, Any]],
        outline: Any,
        platform_config: Dict[str, Any],
        chat_id: Optional[UUID],
        tenant_id: UUID,
        user_id: UUID,
        agent_run_id: UUID,
    ) -> NextStep: ...


# --------------------------------------------------------------------------- #
# Sub-agent execution                                                          #
# --------------------------------------------------------------------------- #


@runtime_checkable
class AgentExecutionPort(Protocol):
    """Executes a single sub-agent step chosen by the planner. Streams
    RuntimeEvents and mutates `memory` (appends AgentResult, facts)."""

    def execute(
        self,
        *,
        step: NextStep,
        memory: WorkingMemory,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Dict[str, Any],
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[RuntimeEvent]: ...


# --------------------------------------------------------------------------- #
# Synthesizer                                                                  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class SynthesizerPort(Protocol):
    """Renders the final answer stream from WorkingMemory."""

    def stream(
        self,
        *,
        memory: WorkingMemory,
        run_id: UUID,
        model: Optional[str] = None,
        planner_hint: Optional[str] = None,
    ) -> AsyncIterator[RuntimeEvent]: ...
