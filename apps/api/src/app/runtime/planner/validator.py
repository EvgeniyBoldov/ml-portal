"""Validation of planner NextStep against available agents and outline state."""
from __future__ import annotations

from typing import Iterable, Optional

from app.runtime.contracts import NextStep, NextStepKind
from app.runtime.memory.working_memory import WorkingMemory


class ValidatorError(ValueError):
    """Planner produced a structurally valid but disallowed step."""


def validate_next_step(
    step: NextStep,
    *,
    allowed_agents: Iterable[str],
    memory: WorkingMemory,
) -> Optional[str]:
    """Return an error message if the step is not executable, otherwise None.

    Caller decides whether to raise, retry, or force a safe fallback.
    """
    allowed = {slug for slug in allowed_agents if slug}

    if step.kind == NextStepKind.CALL_AGENT:
        if not step.agent_slug:
            return "call_agent step missing agent_slug"
        if allowed and step.agent_slug not in allowed:
            return (
                f"agent '{step.agent_slug}' is not in the allowed list: "
                f"{sorted(allowed)}"
            )

    if step.kind == NextStepKind.ASK_USER:
        if not (step.question or "").strip():
            return "ask_user step missing question"

    if step.kind == NextStepKind.FINAL:
        if not (step.final_answer or "").strip():
            return "final step missing final_answer"
        if not memory.can_finalize():
            return "final step blocked: must_do phase is not complete yet"

    if step.kind == NextStepKind.ABORT:
        if not (step.rationale or "").strip():
            return "abort step missing rationale"

    return None
