"""
Runtime ports — Protocols that describe the boundaries of the pipeline.

The pipeline (and its stages) depend on these abstractions, not on concrete
adapters. Concrete adapters live next to them:

    AgentExecutionPort      ← app.runtime.agent_executor.AgentExecutor
    SynthesizerPort         ← app.runtime.synthesizer.Synthesizer
    PlannerPort             ← canonical graph planner
    TaskExecutionPort       ← canonical task attempt executor

Keeping these as Protocols (structural typing) means we do not force existing
adapters to inherit — they already match by method shape.

Post-M6: MemoryPort / TriageServicePort / SummaryPort / WorkingMemory are all gone.
Cross-turn memory is owned by FactStore + SummaryStore via
MemoryBuilder/MemoryWriter; triage was subsumed by the planner; RuntimeTurnState
is the single source of truth for runtime state.
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
from app.runtime.orchestrator_contracts import (
    AgentExecutionResult,
    PlanPatch,
    PlanRequest,
    TaskAttemptFailure,
    TaskRequest,
    PlannerDecisionKind,
)
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.events import RuntimeEvent
from app.runtime.turn_state import RuntimeTurnState


# --------------------------------------------------------------------------- #
# Planner                                                                      #
# --------------------------------------------------------------------------- #
#
# The graph planner is the sole planner boundary.


@runtime_checkable
class PlannerPort(Protocol):
    """Planner boundary for the canonical persisted execution graph."""

    async def plan(self, *, request: PlanRequest, **kwargs: Any) -> PlanPatch: ...


@runtime_checkable
@runtime_checkable
class TaskExecutionPort(Protocol):
    """Executes one agent attempt; the runtime reduces it to task state."""

    async def execute_attempt(self, *, request: TaskRequest, **kwargs: Any) -> AgentExecutionResult: ...


@runtime_checkable
class TaskFailureClassifier(Protocol):
    def classify(self, exc: BaseException) -> TaskAttemptFailure: ...


# --------------------------------------------------------------------------- #
# Sub-agent execution                                                          #
# --------------------------------------------------------------------------- #


@runtime_checkable
# --------------------------------------------------------------------------- #
# Synthesizer                                                                  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class SynthesizerPort(Protocol):
    """Renders the terminal synthesis checkpoint from final-plan context."""

    def stream(
        self,
        *,
        runtime_state: RuntimeTurnState,
        run_id: UUID,
        synthesis_context: Dict[str, Any],
        model: Optional[str] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
    ) -> AsyncIterator[RuntimeEvent]: ...
