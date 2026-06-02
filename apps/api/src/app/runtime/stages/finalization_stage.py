"""
FinalizationStage — synthesizer stream + terminal state flag.

Invoked by the pipeline when PlanningStage reports NEEDS_FINAL (planner
FINAL, loop-detected, max-iters). The planner's DIRECT_ANSWER path
emits its final event inside PlanningStage itself and does NOT come
through here.

Cross-turn memory is owned by FactStore + DialogueSummaryStore via
MemoryBuilder/MemoryWriter; there is nothing left to persist at the
stage level. The RuntimeTurnState is the single source of truth.
"""
from __future__ import annotations

from typing import AsyncIterator, Literal, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.runtime.contracts import PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase
from app.runtime.ports import SynthesizerPort
from app.runtime.turn_state import RuntimeTurnState
from app.runtime.budgets import BudgetRegistry, BudgetResolver

logger = get_logger(__name__)


class FinalizationStage:
    """Produces the final answer stream and flips the turn to terminal."""

    def __init__(
        self,
        *,
        synthesizer: SynthesizerPort,
    ) -> None:
        self._synth = synthesizer

    async def run(
        self,
        *,
        runtime_state: RuntimeTurnState,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize",
        model: Optional[str],
        platform_config: Optional[dict] = None,
        sandbox_overrides: Optional[dict] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        run_synthesizer: bool = True,
        logging_level: Optional[str] = None,
    ) -> AsyncIterator[PhasedEvent]:
        """Drive synthesizer and set the terminal flags."""
        state = runtime_state
        if run_synthesizer:
            async for event in self._synth.stream(
                runtime_state=state,
                run_id=state.run_id,
                model=model,
                planner_hint=planner_hint,
                final_answer_strategy=final_answer_strategy,
                platform_config=platform_config,
                sandbox_overrides=sandbox_overrides,
                budget_registry=budget_registry,
                budget_resolver=budget_resolver,
                logging_level=logging_level,
            ):
                yield PhasedEvent(event, OrchestrationPhase.SYNTHESIS)

        state.status = stop_reason.value
