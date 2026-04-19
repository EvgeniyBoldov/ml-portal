from __future__ import annotations

from uuid import uuid4

from app.runtime.memory.working_memory import PlannerStepRecord, WorkingMemory


def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="goal",
        question="question",
    )


def test_working_memory_add_fact_deduplicates_and_caps():
    memory = _memory()

    memory.add_fact("same fact")
    memory.add_fact("same fact")
    assert len(memory.facts) == 1

    for i in range(100):
        memory.add_fact(f"fact-{i}")

    assert len(memory.facts) <= 40
    assert memory.facts[-1].text == "fact-99"


def test_working_memory_loop_detection_uses_recent_signatures():
    memory = _memory()
    for i in range(3):
        memory.add_planner_step(
            PlannerStepRecord(
                iteration=i + 1,
                kind="call_agent",
                agent_slug="netbox",
                phase_id="discover",
                rationale="r",
                signature="fixed",
            )
        )

    assert memory.iter_count == 3
    assert memory.detect_loop() is True


def test_working_memory_can_finalize_respects_must_do_phases():
    memory = _memory()
    memory.outline = {
        "phases": [
            {"phase_id": "collect", "must_do": True, "allow_final_after": False},
            {"phase_id": "finalize", "must_do": True, "allow_final_after": True},
        ]
    }

    assert memory.can_finalize() is False
    memory.mark_phase_completed("collect")
    assert memory.can_finalize() is True
