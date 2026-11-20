from app.agents.runtime.agent import (
    AgentToolRuntime,
)


def test_terminal_declaration_validation_accepts_json_and_fence():
    declaration = '{"completion":"fulfilled","report":"ok","outputs":{},"needs":[]}'
    assert AgentToolRuntime._has_valid_task_completion_declaration(declaration)
    assert AgentToolRuntime._has_valid_task_completion_declaration(f"```json\n{declaration}\n```")


def test_terminal_declaration_validation_rejects_invalid_contracts():
    assert not AgentToolRuntime._has_valid_task_completion_declaration("Доступны коллекции: Jira и DCBox")
    assert AgentToolRuntime._has_valid_task_completion_declaration(
        '{"completion":"unfulfillable","report":"blocked","outputs":{},"needs":[]}'
    )

