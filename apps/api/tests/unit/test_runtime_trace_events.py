from app.runtime.events import RuntimeEvent, RuntimeEventType


def test_tool_request_and_result_share_a_canonical_entity() -> None:
    request = RuntimeEvent.tool_call(
        tool="file.read",
        call_id="call-1",
        arguments={"artifact_id": "artifact-1"},
        parent_entity_type="agent_run",
        parent_entity_id="agent-1",
    )
    result = RuntimeEvent.tool_result(
        tool="file.read",
        call_id="call-1",
        success=True,
        data={"content": "ok"},
        parent_entity_type="agent_run",
        parent_entity_id="agent-1",
    )

    assert request.type is RuntimeEventType.TOOL_CALL
    assert result.type is RuntimeEventType.TOOL_RESULT
    assert request.data["entity_type"] == result.data["entity_type"] == "tool_call"
    assert request.data["entity_id"] == result.data["entity_id"] == "call-1"
    assert request.data["parent_entity_id"] == result.data["parent_entity_id"] == "agent-1"


def test_agent_start_contains_executor_identity() -> None:
    event = RuntimeEvent.agent_start(
        agent_run_id="planner-1",
        parent_entity_id="iteration-1",
        agent_slug="planner",
        executor_type="planner",
        task_title="Сформировать план",
    )

    assert event.data["executor_type"] == "planner"
    assert event.data["executor_name"] == "Планер"
    assert event.data["task_title"] == "Сформировать план"


def test_interaction_requests_are_children_of_executor_runs() -> None:
    clarify = RuntimeEvent.waiting_input(
        "Какой проект?",
        entity_id="planner-1:interaction",
        parent_entity_type="agent_run",
        parent_entity_id="planner-1",
    )
    confirm = RuntimeEvent.confirmation_required(
        "Подтвердить запись",
        entity_id="agent-1:interaction",
        parent_entity_type="agent_run",
        parent_entity_id="agent-1",
    )

    assert clarify.data["entity_type"] == confirm.data["entity_type"] == "interaction"
    assert clarify.data["interaction_kind"] == "clarify"
    assert confirm.data["interaction_kind"] == "confirm"
    assert clarify.data["parent_entity_id"] == "planner-1"
    assert confirm.data["parent_entity_id"] == "agent-1"
