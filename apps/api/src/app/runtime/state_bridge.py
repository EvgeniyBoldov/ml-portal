"""Compatibility bridge between legacy WorkingMemory and RuntimeTurnState.

This module keeps old test/import contracts working while runtime code
uses RuntimeTurnState as the canonical state.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime.memory.components import MemoryBundle
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.turn_state import RuntimeFact, RuntimeTurnState


_RUNTIME_STATE_KEY = "runtime_turn_state"


def _fact_to_dict(item: Any) -> Dict[str, str]:
    text = str(getattr(item, "text", "") or "").strip()
    source = str(getattr(item, "source", "") or "planner")
    return {"text": text, "source": source}


def _planner_step_to_dict(item: Any) -> Dict[str, Any]:
    return {
        "iteration": int(getattr(item, "iteration", 0) or 0),
        "kind": str(getattr(item, "kind", "") or ""),
        "agent_slug": getattr(item, "agent_slug", None),
        "phase_id": getattr(item, "phase_id", None),
        "rationale": str(getattr(item, "rationale", "") or ""),
    }


def _agent_result_to_dict(item: Any) -> Dict[str, Any]:
    return {
        "agent_slug": str(getattr(item, "agent_slug", "") or ""),
        "summary": str(getattr(item, "summary", "") or ""),
        "facts": list(getattr(item, "facts", []) or []),
        "phase_id": getattr(item, "phase_id", None),
        "iteration": int(getattr(item, "iteration", 0) or 0),
        "success": bool(getattr(item, "success", True)),
        "error": getattr(item, "error", None),
    }


def _persist_runtime_state(memory: WorkingMemory, state: RuntimeTurnState) -> None:
    memory.memory_state[_RUNTIME_STATE_KEY] = state.model_dump(mode="json")


def sync_runtime_turn_state_from_legacy(
    *,
    memory: WorkingMemory,
    current_user_query: Optional[str] = None,
) -> RuntimeTurnState:
    """Build RuntimeTurnState from current WorkingMemory fields."""
    query = memory.question if current_user_query is None else current_user_query
    state = RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal=memory.goal or "",
        current_user_query=query or "",
        memory_bundle=MemoryBundle(),
    )
    state.outline = memory.outline
    state.current_phase_id = memory.current_phase_id
    state.completed_phase_ids = list(memory.completed_phase_ids or [])
    state.blocked_phase_ids = list(memory.blocked_phase_ids or [])
    state.open_questions = list(memory.open_questions or [])
    state.status = memory.status or "running"
    state.final_answer = memory.final_answer
    state.final_error = memory.final_error
    state.iter_count = int(memory.iter_count or 0)
    state.used_tool_calls = int(memory.used_tool_calls or 0)
    state.recent_action_signatures = list(memory.recent_action_signatures or [])
    state.runtime_facts = [
        RuntimeFact.model_validate(_fact_to_dict(item))
        for item in (memory.facts or [])
        if getattr(item, "text", "").strip()
    ]
    state.planner_steps = [_planner_step_to_dict(item) for item in (memory.planner_steps or [])]
    state.agent_results = [_agent_result_to_dict(item) for item in (memory.agent_results or [])]
    state.tool_ledger = memory.tool_ledger
    _persist_runtime_state(memory, state)
    return state


def ensure_runtime_turn_state(memory: WorkingMemory) -> RuntimeTurnState:
    """Return RuntimeTurnState cached in memory_state or build from legacy fields."""
    raw = memory.memory_state.get(_RUNTIME_STATE_KEY)
    if isinstance(raw, dict):
        try:
            state = RuntimeTurnState.model_validate(raw)
            _persist_runtime_state(memory, state)
            return state
        except Exception:
            # Fall through to re-sync from legacy state.
            pass
    return sync_runtime_turn_state_from_legacy(memory=memory, current_user_query=memory.question)
