from uuid import uuid4

from app.runtime.memory.components import MemoryBundle
from app.runtime.turn_state import RuntimeTurnState


def test_turn_state_keeps_the_most_detailed_agent_observation_level() -> None:
    state = RuntimeTurnState.from_seed(
        run_id=uuid4(), chat_id=None, user_id=None, tenant_id=None,
        goal="test", current_user_query="test", memory_bundle=MemoryBundle(),
    )

    state.register_descendant_logging_level("brief")
    state.register_descendant_logging_level("full")
    state.register_descendant_logging_level("none")

    assert state.descendant_logging_level == "full"
