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


def test_runtime_turn_state_loop_detection_and_snapshot():
    state = _state()
    state.add_runtime_fact("f1", source="planner")
    state.add_agent_result({"agent_slug": "a", "summary": "ok", "success": True})
    state.add_planner_step({"kind": "call_agent", "agent_slug": "a", "phase_id": "p1"})
    state.add_planner_step({"kind": "call_agent", "agent_slug": "a", "phase_id": "p1"})
    state.add_planner_step({"kind": "call_agent", "agent_slug": "a", "phase_id": "p1"})

    snap = state.planner_snapshot()
    assert snap["iter_count"] == 3
    assert snap["facts"] == ["f1"]
    assert state.detect_loop() is True


def test_runtime_turn_state_loop_detection_distinguishes_agent_query():
    state = _state()
    state.add_planner_step(
        {
            "kind": "call_agent",
            "agent_slug": "a",
            "phase_id": "p1",
            "agent_input": {"query": "find incidents in dc-1"},
        }
    )
    state.add_planner_step(
        {
            "kind": "call_agent",
            "agent_slug": "a",
            "phase_id": "p1",
            "agent_input": {"query": "find incidents in dc-2"},
        }
    )
    state.add_planner_step(
        {
            "kind": "call_agent",
            "agent_slug": "a",
            "phase_id": "p1",
            "agent_input": {"query": "find incidents in dc-3"},
        }
    )

    assert state.detect_loop() is False


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
