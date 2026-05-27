from app.agents.runtime.agent import AgentToolRuntime


def test_intent_message_uses_defaults():
    assert (
        AgentToolRuntime._intent_message(
            key="agent_start",
            platform_config={},
            sandbox_overrides={},
        )
        == "Запускаю выполнение агента"
    )


def test_intent_message_uses_platform_override():
    msg = AgentToolRuntime._intent_message(
        key="final_answer",
        platform_config={"intent_messages": {"final_answer": "Finalize now"}},
        sandbox_overrides={},
    )
    assert msg == "Finalize now"


def test_intent_message_sandbox_override_has_priority_and_formats():
    msg = AgentToolRuntime._intent_message(
        key="operation_call",
        platform_config={"intent_messages": {"operation_call": "Platform {operation_slug}"}},
        sandbox_overrides={"intent_messages": {"operation_call": "Sandbox op {operation_slug}"}},
        operation_slug="collection.search",
    )
    assert msg == "Sandbox op collection.search"

