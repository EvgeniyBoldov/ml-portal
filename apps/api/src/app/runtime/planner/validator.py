"""Validation of planner NextStep against available agents and outline state."""
from __future__ import annotations

from typing import Iterable, Optional

from app.runtime.contracts import NextStep, NextStepKind
from app.runtime.planner.iteration_policy import (
    has_previous_sufficient_call_agent,
    has_repeated_pending_question,
    should_block_repeated_call_agent_after_success,
)
from app.runtime.turn_state import RuntimeTurnState


class ValidatorError(ValueError):
    """Planner produced a structurally valid but disallowed step."""


def validate_next_step(
    step: NextStep,
    *,
    allowed_agents: Iterable[str],
    runtime_state: RuntimeTurnState,
) -> Optional[str]:
    """Return an error message if the step is not executable, otherwise None.

    Caller decides whether to raise, retry, or force a safe fallback.
    """
    allowed = {slug for slug in allowed_agents if slug}

    if step.kind == NextStepKind.CALL_AGENT:
        if not step.agent_slug:
            return "call_agent step missing agent_slug"
        if not allowed:
            return "call_agent step blocked: no allowed agents available"
        if allowed and step.agent_slug not in allowed:
            return (
                f"agent '{step.agent_slug}' is not in the allowed list: "
                f"{sorted(allowed)}"
            )
        if should_block_repeated_call_agent_after_success(
            runtime_state,
            agent_slug=step.agent_slug,
            phase_id=step.phase_id,
        ):
            return "call_agent step blocked: previous successful result for this phase is already sufficient"

    if step.kind in (NextStepKind.ASK_USER, NextStepKind.CLARIFY):
        question = (step.question or "").strip()
        if not question:
            return f"{step.kind.value} step missing question"
        question_lc = " ".join(question.lower().split())
        if any(" ".join(str(item or "").lower().split()) == question_lc for item in runtime_state.open_questions):
            return f"{step.kind.value} step repeats an already asked question"
        if has_repeated_pending_question(runtime_state, question):
            return f"{step.kind.value} step repeats pending question from previous iteration"
        # If the previous iteration already produced a sufficient successful result,
        # clarify is usually a planner regression.
        if has_previous_sufficient_call_agent(runtime_state):
            return f"{step.kind.value} step blocked: previous agent result is already sufficient"

    if step.kind == NextStepKind.FINAL:
        if not (step.final_answer or "").strip():
            return "final step missing final_answer"
        if not runtime_state.can_finalize():
            return "final step blocked: must_do phase is not complete yet"

    if step.kind == NextStepKind.ABORT:
        if not (step.rationale or "").strip():
            return "abort step missing rationale"

    return None
