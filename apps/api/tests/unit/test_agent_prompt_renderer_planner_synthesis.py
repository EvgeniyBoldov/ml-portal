from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer


def test_build_planner_synthesis_messages_returns_expected_structure():
    messages = AgentPromptRenderer.build_planner_synthesis_messages(
        original_messages=[{"role": "user", "content": "q"}],
        facts_text="fact-1; fact-2",
    )

    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert "Синтезируй финальный ответ" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "q"}
    assert messages[2]["role"] == "user"
    assert "fact-1; fact-2" in messages[2]["content"]

