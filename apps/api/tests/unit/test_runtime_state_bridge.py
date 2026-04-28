from __future__ import annotations

from uuid import uuid4

from app.runtime.memory.working_memory import AgentResult, PlannerStepRecord, WorkingMemory
from app.runtime.state_bridge import ensure_runtime_turn_state, sync_runtime_turn_state_from_legacy


def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="goal",
        question="question",
        status="running",
    )


def test_state_bridge_ensure_creates_runtime_state():
    memory = _memory()
    state = ensure_runtime_turn_state(memory)
    assert state.goal == "goal"
    assert "runtime_turn_state" in memory.memory_state


def test_state_bridge_sync_copies_legacy_fields():
    memory = _memory()
    memory.add_fact("fact one", source="planner")
    memory.add_planner_step(
        PlannerStepRecord(
            iteration=1,
            kind="call_agent",
            agent_slug="a",
            phase_id="p1",
            rationale="r",
        )
    )
    memory.add_agent_result(
        AgentResult(
            agent_slug="a",
            summary="ok",
            success=True,
            phase_id="p1",
            iteration=1,
        )
    )
    memory.status = "waiting_input"
    memory.current_phase_id = "p1"
    memory.completed_phase_ids = ["p1"]
    memory.outline = {"phases": [{"phase_id": "p1", "must_do": True}]}
    memory.add_open_question("what next?")

    state = sync_runtime_turn_state_from_legacy(memory=memory, current_user_query="q2")
    assert state.status == "waiting_input"
    assert state.current_user_query == "q2"
    assert state.runtime_facts
    assert state.planner_steps[-1]["kind"] == "call_agent"
    assert state.agent_results[-1]["agent_slug"] == "a"
    assert state.open_questions == ["what next?"]
    assert state.current_phase_id == "p1"
    assert state.completed_phase_ids == ["p1"]
    assert state.can_finalize() is True
