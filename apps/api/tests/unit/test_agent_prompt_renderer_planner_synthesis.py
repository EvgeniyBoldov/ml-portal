from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer


def test_build_synthesis_messages_returns_expected_structure():
    messages = AgentPromptRenderer.build_synthesis_messages(
        agent_prompt="Agent prompt",
        original_messages=[{"role": "user", "content": "q"}],
        observation_text="fact-1; fact-2",
    )

    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Agent prompt"
    assert messages[1] == {"role": "user", "content": "q"}
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert "fact-1; fact-2" in messages[3]["content"]
