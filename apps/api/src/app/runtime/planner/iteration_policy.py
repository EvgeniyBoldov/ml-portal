from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime.contracts import NextStepKind
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.turn_state import RuntimeTurnState


def resolve_agent_outcome(*, success: bool) -> str:
    return "success" if success else "failed"


def resolve_sufficient_for_phase(
    *,
    success: bool,
    summary: str,
    missing_inputs: Optional[list[str]] = None,
) -> bool:
    if not success:
        return False
    if missing_inputs:
        return False
    return bool((summary or "").strip())


def latest_iteration_signature(state: RuntimeTurnState) -> str:
    if not state.recent_action_signatures:
        return ""
    return state.recent_action_signatures[-1]


def build_iteration_result(
    *,
    state: RuntimeTurnState,
    iteration: int,
    step_kind: str,
    agent_slug: Optional[str],
    phase_id: Optional[str],
    outcome: str,
    summary: str = "",
    question: Optional[str] = None,
    missing_inputs: Optional[list[str]] = None,
    sufficient_for_phase: bool = False,
    retryable: Optional[bool] = None,
    error_code: Optional[str] = None,
    status: Optional[str] = None,
    needs: Optional[list[Dict[str, Any]]] = None,
    completion_kind: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "iteration": iteration,
        "step_kind": step_kind,
        "agent_slug": agent_slug,
        "phase_id": phase_id,
        "outcome": outcome,
        "summary": (summary or "")[:800],
        "question": question,
        "missing_inputs": list(missing_inputs or []),
        "sufficient_for_phase": bool(sufficient_for_phase),
        "retryable": retryable,
        "error_code": error_code,
        "status": status,
        "needs": list(needs or []),
        "completion_kind": completion_kind,
        "signature": latest_iteration_signature(state),
    }


def has_previous_sufficient_call_agent(state: RuntimeTurnState) -> bool:
    last = state.latest_iteration_result()
    if last is None:
        return False
    return (
        str(last.step_kind) == NextStepKind.CALL_AGENT.value
        and str(last.outcome) == "success"
        and bool(last.sufficient_for_phase)
    )


def classify_agent_failure(
    state: RuntimeTurnState,
    *,
    agent_slug: Optional[str],
) -> Dict[str, bool]:
    """Classify latest agent outcome for planner control flow.

    Returns:
        {"non_retryable": bool, "unavailable": bool}
    """
    latest = latest_call_agent_iteration(state)
    if latest:
        latest_slug = str(latest.get("agent_slug") or "")
        if agent_slug and latest_slug and latest_slug != agent_slug:
            return {"non_retryable": False, "unavailable": False}
        if str(latest.get("outcome")) == "success":
            return {"non_retryable": False, "unavailable": False}
        retryable = latest.get("retryable")
        error_code = str(latest.get("error_code") or "")
        if error_code in {
            RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
            RuntimeErrorCode.AGENT_UNAVAILABLE.value,
            RuntimeErrorCode.AGENT_NO_OPERATIONS.value,
        }:
            return {"non_retryable": True, "unavailable": True}
        if retryable is False:
            return {"non_retryable": True, "unavailable": False}
        if error_code in {
            RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
            RuntimeErrorCode.OPERATION_AMBIGUOUS.value,
            RuntimeErrorCode.AGENT_NON_RETRYABLE_OPERATION_FAILURE.value,
            RuntimeErrorCode.AGENT_REQUIRED_OPERATION_CALL_MISSING.value,
            RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED.value,
            RuntimeErrorCode.AGENT_WALL_TIME_EXCEEDED.value,
        }:
            return {"non_retryable": True, "unavailable": False}
        return {"non_retryable": False, "unavailable": False}
    return {"non_retryable": False, "unavailable": False}


def latest_call_agent_iteration(state: RuntimeTurnState) -> Dict[str, Any]:
    last = state.latest_iteration_result()
    if last is None:
        return {}
    if str(last.step_kind) != NextStepKind.CALL_AGENT.value:
        return {}
    return {
        "agent_slug": last.agent_slug,
        "phase_id": last.phase_id,
        "outcome": last.outcome,
        "summary": last.summary,
        "missing_inputs": list(last.missing_inputs or []),
        "sufficient_for_phase": bool(last.sufficient_for_phase),
        "retryable": last.retryable,
        "error_code": last.error_code or "",
        "status": last.status or "",
        "needs": list(last.needs or []),
        "completion_kind": last.completion_kind or "",
    }


def latest_agent_result_payload(
    state: RuntimeTurnState,
    *,
    iteration: int,
    agent_slug: Optional[str],
    phase_id: Optional[str],
) -> Dict[str, Any]:
    """Return raw agent_result payload for the current CALL_AGENT step.

    Chooses the newest record that matches current iteration and optional
    agent/phase constraints. This keeps planning_stage independent from
    legacy payload layout and prevents accidental reuse of previous iteration.
    """
    results = list(state.agent_results or [])
    for item in reversed(results):
        if not isinstance(item, dict):
            continue
        item_iteration = int(item.get("iteration") or 0)
        if item_iteration != int(iteration):
            continue
        item_slug = str(item.get("agent_slug") or item.get("agent") or "")
        if agent_slug and item_slug and item_slug != agent_slug:
            continue
        item_phase = str(item.get("phase_id") or "")
        if phase_id and item_phase and item_phase != str(phase_id):
            continue
        return dict(item)
    return {}


def has_repeated_pending_question(state: RuntimeTurnState, question: str) -> bool:
    target = " ".join(str(question or "").lower().split())
    if not target:
        return False
    for item in reversed(state.iteration_results):
        if str(item.outcome) != "needs_input":
            continue
        raw = " ".join(str(item.question or "").lower().split())
        if raw == target:
            return True
    return False


def should_block_repeated_call_agent_after_success(
    state: RuntimeTurnState,
    *,
    agent_slug: Optional[str],
    phase_id: Optional[str],
) -> bool:
    latest = latest_call_agent_iteration(state)
    if not latest:
        return False
    if str(latest.get("outcome")) != "success":
        return False
    if not bool(latest.get("sufficient_for_phase")):
        return False
    latest_slug = str(latest.get("agent_slug") or "")
    latest_phase = str(latest.get("phase_id") or "")
    step_slug = str(agent_slug or "")
    step_phase = str(phase_id or "")
    if latest_slug and step_slug and latest_slug != step_slug:
        return False
    if latest_phase and step_phase and latest_phase != step_phase:
        return False
    return True
