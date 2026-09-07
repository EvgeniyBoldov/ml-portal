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
    assert state.runtime_facts[0].text == "f1"


def test_runtime_turn_state_compact_view_is_serializable():
    state = _state()
    state.status = "completed"
    state.final_answer = "ready"
    payload = state.compact_view()
    assert payload["status"] == "completed"
    assert payload["final_answer"] == "ready"
    assert "memory_bundle" in payload
