from app.agents.runtime.agent import (
    AgentToolRuntime,
    DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION,
)


def test_terminal_declaration_validation_accepts_json_and_fence():
    declaration = '{"completion":"fulfilled","report":"ok","outputs":{},"needs":[]}'
    assert AgentToolRuntime._has_valid_task_completion_declaration(declaration)
    assert AgentToolRuntime._has_valid_task_completion_declaration(f"```json\n{declaration}\n```")


def test_terminal_declaration_validation_rejects_invalid_contracts():
    assert not AgentToolRuntime._has_valid_task_completion_declaration("Доступны коллекции: Jira и DCBox")
    assert not AgentToolRuntime._has_valid_task_completion_declaration(
        '{"completion":"unfulfillable","report":"blocked","outputs":{},"needs":[]}'
    )


def test_required_operation_retry_instruction_uses_default():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={},
        sandbox_overrides={},
    )
    assert text == DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION


def test_required_operation_retry_instruction_uses_platform_config():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={"retry_instruction": "platform instruction"},
        sandbox_overrides={},
    )
    assert text == "platform instruction"


def test_required_operation_retry_instruction_sandbox_override_priority():
    text = AgentToolRuntime._required_operation_retry_instruction(
        platform_config={"retry_instruction": "platform instruction"},
        sandbox_overrides={"required_operation_retry_instruction": "sandbox instruction"},
    )
    assert text == "sandbox instruction"
