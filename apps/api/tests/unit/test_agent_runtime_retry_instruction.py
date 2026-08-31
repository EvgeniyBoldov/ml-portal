from app.agents.runtime.agent import (
    AgentToolRuntime,
    AgentLoopState,
    DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION,
)
from app.agents.context import ToolCall, ToolResult
from types import SimpleNamespace


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


def test_successful_collection_info_activates_only_returned_tools():
    info = SimpleNamespace(
        operation_slug="instance.jira.collection.info",
        operation="collection.info",
        name="Collection Info",
        description="",
        input_schema={},
        collection_slug="jira",
        scope="collection",
    )
    search = SimpleNamespace(
        operation_slug="instance.jira.collection.ticket.search",
        operation="collection.ticket.search",
        name="Search tickets",
        description="",
        input_schema={},
        collection_slug="jira",
        scope="collection",
    )
    hidden = SimpleNamespace(
        operation_slug="instance.jira.collection.ticket.write",
        operation="collection.ticket.write",
        name="Write ticket",
        description="",
        input_schema={},
        collection_slug="jira",
        scope="collection",
    )
    loop_state = AgentLoopState()

    AgentToolRuntime._activate_collection_tools(
        operation_call=ToolCall(
            id="info", tool_name="collection.info", arguments={"collection_slug": "jira"}
        ),
        result=ToolResult.ok({
            "collection": {"slug": "jira"},
            # collection.info publishes the canonical operation name; the
            # runtime maps it to its opaque provider-scoped operation slug.
            "tools": [{"invoke_as": search.operation}],
        }),
        available_operations=[info, search, hidden],
        loop_state=loop_state,
    )

    assert loop_state.opened_collections == {"jira"}
    assert loop_state.active_collection_operation_slugs == {search.operation_slug}
