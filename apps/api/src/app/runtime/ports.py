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
MemoryBuilder/MemoryWriter; triage was subsumed by the planner; rolling
summary is done by SummaryCompactor inside MemoryWriter; RuntimeTurnState
is the single source of truth for runtime state.
"""
from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    runtime_checkable,
)
from uuid import UUID

from app.agents.context import ToolContext
from app.runtime.contracts import NextStep
from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
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
# Post-M5: TriageServicePort removed. The planner is the sole decision
# engine — clarify / call_agent / final / abort all come
# from a single `next_step` call. SummaryPort removed too — rolling
# summary is owned by `MemoryWriter` + `SummaryCompactor` now.


@runtime_checkable
class PlannerPort(Protocol):
    """Planner boundary for the canonical persisted execution graph."""

    async def plan(self, *, request: PlanRequest, **kwargs: Any) -> PlanPatch: ...


@runtime_checkable
class NextStepPlannerPort(Protocol):
    """Planner boundary for the chat turn planner loop."""

    async def next_step(self, **kwargs: Any) -> Any: ...


@runtime_checkable
class TaskExecutionPort(Protocol):
    """Executes a logical task attempt and returns a strict agent result."""

    async def execute_task(self, *, request: TaskRequest, **kwargs: Any) -> AgentTaskResult: ...


@runtime_checkable
class TaskFailureClassifier(Protocol):
    def classify(self, exc: BaseException) -> TaskAttemptFailure: ...


# --------------------------------------------------------------------------- #
# Sub-agent execution                                                          #
# --------------------------------------------------------------------------- #


@runtime_checkable
class AgentExecutionPort(Protocol):
    """Executes a single sub-agent step chosen by the planner. Streams
    RuntimeEvents and mutates `runtime_state` (appends AgentResult, facts)."""

    def execute(
        self,
        *,
        step: NextStep,
        lifecycle_agent_run_id: str,
        runtime_state: RuntimeTurnState,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Dict[str, Any],
        model: Optional[str] = None,
        agent_version_id: Optional[UUID] = None,
    ) -> AsyncIterator[RuntimeEvent]: ...


# --------------------------------------------------------------------------- #
# Synthesizer                                                                  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class SynthesizerPort(Protocol):
    """Renders the final answer stream from RuntimeTurnState."""

    def stream(
        self,
        *,
        runtime_state: RuntimeTurnState,
        run_id: UUID,
        model: Optional[str] = None,
        answer_brief: Optional[str] = None,
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize",
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
    ) -> AsyncIterator[RuntimeEvent]: ...
