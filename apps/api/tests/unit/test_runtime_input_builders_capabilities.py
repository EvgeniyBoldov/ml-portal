from __future__ import annotations

from uuid import uuid4

from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.memory.components import MemoryBundle
from app.runtime.turn_state import RuntimeTurnState


def test_planner_input_builder_preserves_optional_agent_capability_summary():
    state = RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="goal",
        current_user_query="query",
        memory_bundle=MemoryBundle(),
    )

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[
            {
                "slug": "net.enginer",
                "description": "network agent",
                "capability_summary": "Работает с регламентами и шаблонами конфигов",
                "collections": ["reglament", "network_templates"],
                "system_operations": ["file.generate"],
            }
        ],
        outline=None,
        platform_config={},
    )

    assert payload["available_agents"][0]["capability_summary"] == "Работает с регламентами и шаблонами конфигов"
    assert payload["available_agents"][0]["collections"] == ["reglament", "network_templates"]
    assert payload["available_agents"][0]["system_operations"] == ["file.generate"]
