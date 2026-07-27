from __future__ import annotations

from uuid import uuid4

from app.runtime.memory.components import MemoryBundle
from app.runtime.turn_state import RuntimeTurnState


def _state() -> RuntimeTurnState:
    return RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="runtime goal",
        current_user_query="runtime question",
        memory_bundle=MemoryBundle(),
    )


def test_runtime_turn_state_snapshot_preserves_runtime_facts():
    state = _state()
    state.add_runtime_fact("f1", source="planner")
    state.add_agent_result({"agent_slug": "a", "summary": "ok", "success": True})

    snap = state.planner_snapshot()
    assert snap["facts"] == ["f1"]


def test_runtime_turn_state_compact_view_is_serializable():
    state = _state()
    state.status = "completed"
    state.final_answer = "ready"
    payload = state.compact_view()
    assert payload["status"] == "completed"
    assert payload["final_answer"] == "ready"
    assert "memory_bundle" in payload


def test_runtime_turn_state_can_finalize_with_outline():
    state = _state()
    state.outline = {
        "phases": [
            {"phase_id": "p1", "must_do": True},
            {"phase_id": "p2", "must_do": False},
        ]
    }
    assert state.can_finalize() is False
    state.completed_phase_ids = ["p1"]
    assert state.can_finalize() is True
