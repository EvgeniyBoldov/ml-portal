"""
Runtime ports — Protocols that describe the boundaries of the pipeline.

The pipeline (and its stages) depend on these abstractions, not on concrete
adapters. Concrete adapters live next to them:

    AgentExecutionPort      ← app.runtime.agent_executor.AgentExecutor
    SynthesizerPort         ← app.runtime.synthesizer.Synthesizer
    PlannerServicePort      ← app.runtime.planner.planner.Planner

Keeping these as Protocols (structural typing) means we do not force existing
adapters to inherit — they already match by method shape.

Post-M6: MemoryPort / TriageServicePort / SummaryPort are all gone.
Cross-turn memory is owned by FactStore + SummaryStore via
MemoryBuilder/MemoryWriter; triage was subsumed by the planner; rolling
summary is done by SummaryCompactor inside MemoryWriter.
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
from app.runtime.contracts import NextStep
from app.runtime.events import RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory


# --------------------------------------------------------------------------- #
# Planner                                                                      #
# --------------------------------------------------------------------------- #
#
# Post-M5: TriageServicePort removed. The planner is the sole decision
# engine — direct_answer / clarify / call_agent / final / abort all come
# from a single `next_step` call. SummaryPort removed too — rolling
# summary is owned by `MemoryWriter` + `SummaryCompactor` now.


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
