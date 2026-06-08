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
from app.runtime.error_surface import (
    build_user_safe_error_message,
    looks_internal_error_text,
)
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
        answer_brief: Optional[str],
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
        resolved_answer_brief = self._resolve_answer_brief(
            runtime_state=state,
            explicit_answer_brief=answer_brief,
            stop_reason=stop_reason,
        )
        state.answer_brief = resolved_answer_brief
        if run_synthesizer:
            async for event in self._synth.stream(
                runtime_state=state,
                run_id=state.run_id,
                model=model,
                answer_brief=resolved_answer_brief,
                final_answer_strategy=final_answer_strategy,
                platform_config=platform_config,
                sandbox_overrides=sandbox_overrides,
                budget_registry=budget_registry,
                budget_resolver=budget_resolver,
                logging_level=logging_level,
            ):
                yield PhasedEvent(event, OrchestrationPhase.SYNTHESIS)

        state.status = stop_reason.value

    @staticmethod
    def _resolve_answer_brief(
        *,
        runtime_state: RuntimeTurnState,
        explicit_answer_brief: Optional[str],
        stop_reason: PipelineStopReason,
    ) -> str:
        explicit = str(explicit_answer_brief or "").strip()
        if explicit:
            if stop_reason != PipelineStopReason.COMPLETED and looks_internal_error_text(explicit):
                latest_failure = FinalizationStage._latest_failure(runtime_state)
                return build_user_safe_error_message(
                    retryable=latest_failure.get("retryable"),
                    error_code=latest_failure.get("error_code"),
                )
            return explicit

        successful_summaries: list[str] = []
        for item in runtime_state.agent_results:
            if not bool(item.get("success", True)):
                continue
            summary = str(item.get("summary") or "").strip()
            if summary:
                successful_summaries.append(summary)
        if successful_summaries:
            return "\n\n".join(successful_summaries)

        fact_lines = [
            item.text.strip()
            for item in runtime_state.runtime_facts
            if str(item.text or "").strip() and str(item.source or "") != "pipeline_internal"
        ]
        if fact_lines:
            return "\n".join(f"- {line}" for line in fact_lines[-12:])

        latest_failure = FinalizationStage._latest_failure(runtime_state)
        if latest_failure:
            return build_user_safe_error_message(
                retryable=latest_failure.get("retryable"),
                error_code=latest_failure.get("error_code"),
            )

        final_error = str(runtime_state.final_error or "").strip()
        if final_error:
            if looks_internal_error_text(final_error):
                return build_user_safe_error_message(retryable=None, error_code=None)
            return f"Не удалось завершить запрос. {final_error}"
        return "Не удалось собрать достаточные данные для ответа."

    @staticmethod
    def _latest_failure(runtime_state: RuntimeTurnState) -> dict:
        for item in reversed(runtime_state.agent_results):
            if isinstance(item, dict) and not bool(item.get("success", True)):
                return dict(item)
        return {}
