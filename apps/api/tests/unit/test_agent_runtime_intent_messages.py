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
        key="tool_call",
        platform_config={"intent_messages": {"tool_call": "Platform {tool_name}"}},
        sandbox_overrides={"intent_messages": {"tool_call": "Sandbox op {tool_name}"}},
        tool_name="collection.search",
    )
    assert msg == "Sandbox op collection.search"
