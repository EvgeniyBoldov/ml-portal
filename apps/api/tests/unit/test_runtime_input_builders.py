from __future__ import annotations

from uuid import uuid4
from types import SimpleNamespace

from app.runtime.input_builders import PlannerInputBuilder, SynthesizerInputBuilder
from app.runtime.memory.components import MemoryBundle
from app.runtime.turn_state import RuntimeTurnState


def _memory():
    return SimpleNamespace(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="legacy goal",
        question="legacy q",
        status="running",
        memory_state={},
    )


def test_planner_input_builder_prefers_runtime_turn_state_snapshot():
    memory = _memory()
    state = RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal="canonical goal",
        current_user_query="canonical q",
        memory_bundle=MemoryBundle(),
    )
    state.add_runtime_fact("runtime fact")
    memory.memory_state["runtime_turn_state"] = state.model_dump(mode="json")

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[{"slug": "a", "description": "agent"}],
        outline=None,
        platform_config={},
    )
    assert payload["goal"] == "canonical goal"
    assert payload["current_user_query"] == "canonical q"
    assert payload["memory"]["facts"] == ["runtime fact"]


def test_planner_input_builder_includes_structured_continuation():
    state = RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="original goal",
        current_user_query="[confirmation]",
        memory_bundle=MemoryBundle(),
        continuation={
            "mode": "resume",
            "resume_action": "confirm",
            "original_goal": "original goal",
            "paused_context": {"question": "Выполнить опасную операцию?"},
            "user_response": "[confirmation]",
        },
    )

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[],
        outline=None,
        platform_config={},
    )

    assert payload["continuation"]["mode"] == "resume"
    assert payload["continuation"]["resume_action"] == "confirm"
    assert payload["continuation"]["original_goal"] == "original goal"


def test_synthesizer_input_builder_includes_memory_sections_hint():
    memory = _memory()
    state = RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal="canonical goal",
        current_user_query="canonical q",
        memory_bundle=state_memory_bundle(),
    )
    memory.memory_state["runtime_turn_state"] = state.model_dump(mode="json")

    messages = SynthesizerInputBuilder().build(
        runtime_state=state,
        planner_hint="hint",
        system_prompt="sys",
    )
    assert messages[0]["content"] == "sys"
    assert "Отобранная память" in messages[1]["content"]


def state_memory_bundle():
    from app.runtime.memory.components import MemoryBundle, MemoryItem, MemorySection

    return MemoryBundle(
        sections=[
            MemorySection(
                name="facts",
                priority=10,
                items=[MemoryItem(text="x", source="s")],
                budget_used_chars=1,
            )
        ]
    )
