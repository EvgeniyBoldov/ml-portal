from app.agents.runtime.agent import (
    AgentToolRuntime,
    DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION,
)


def test_required_operation_retry_instruction_uses_default():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={},
        sandbox_overrides={},
    )
    assert text == DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION


def test_required_operation_retry_instruction_uses_platform_config():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={"required_operation_retry_instruction": "platform instruction"},
        sandbox_overrides={},
    )
    assert text == "platform instruction"


def test_required_operation_retry_instruction_sandbox_override_priority():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={"required_operation_retry_instruction": "platform instruction"},
        sandbox_overrides={"required_operation_retry_instruction": "sandbox instruction"},
    )
    assert text == "sandbox instruction"

