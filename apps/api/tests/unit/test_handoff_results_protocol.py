from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import RuntimeDependencies, ToolCall, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.runtime.result_context import ResultObservation
from app.agents.runtime.result_workspace_tools import with_workspace_operations
from app.agents.runtime.tools import ToolExecutor
from app.agents.operation_executor import _meaningful_mcp_content
from app.services.result_workspace import _describe_children, _json_pointer
from app.services.tool_result_protocol import normalize_result
from app.services.chat_context_contracts import ResultObservationPayload


def test_collection_search_initial_page_is_not_source_coverage_failure() -> None:
    page = normalize_result(
        {"rows": [{"id": 1}], "total": 2, "has_more": True},
        "collection.search",
        {"offset": 0, "limit": 1},
    )

    assert page.meta.complete is False
    assert getattr(page.meta, "coverage_incomplete", None) is None
    assert page.meta.next_arguments == {"offset": 1, "limit": 1}


def test_result_observation_preserves_unknown_and_nested_reader_cursor() -> None:
    assert ResultObservationPayload is ResultObservation
    observation = ResultObservation.from_mapping({
        "result_id": "r1", "revision": 3, "offset": 0, "limit": 1,
        "source_complete": None, "query_complete": None,
        "path": "/report", "text_offset": 120, "text_limit": 500,
        "next_text_offset": 620, "view": "children", "untrusted_extra": "ignored",
    })

    serialized = observation.model_dump(mode="json", exclude_none=False)
    assert serialized["source_complete"] is None
    assert serialized["query_complete"] is None
    assert serialized["path"] == "/report"
    assert serialized["next_text_offset"] == 620
    assert serialized["view"] == "children"
    assert "untrusted_extra" not in serialized


def test_history_and_import_are_native_workspace_operations_without_source_tools() -> None:
    operations = {item.operation_slug for item in with_workspace_operations([])}
    assert {"result.history", "result.import", "result.describe", "result.read"} <= operations


def test_import_formatter_keeps_provenance_and_does_not_treat_receipt_as_dataset_row() -> None:
    from app.agents.runtime.tools import OperationExecutionFacade
    result = ToolResult.ok({"status": "imported", "result_id": "target", "revision": 1,
        "next_action": {"tool": "result.read", "arguments": {"result_id": "target",
            "revision": 1, "offset": 0, "limit": 20, "view": "auto"}}}, workspace_view=True)
    rendered = OperationExecutionFacade.format_result_for_context(result,
        operation_slug="result.import", stored_result={"result_id": "target", "revision": 1,
            "row_count": 3, "source_total": 3, "source_complete": True, "snapshot_only": True,
            "imported_from": {"source_run_id": "previous"}})
    import json
    view = json.loads(rendered)
    assert "records" not in view
    assert view["snapshot_only"] is True
    assert view["imported_from"]["source_run_id"] == "previous"
    assert view["next_action"]["arguments"]["view"] == "auto"


def test_json_pointer_children_are_bounded_and_escape_paths() -> None:
    payload = {"a/b": {"~key": "value"}, "second": [1, 2]}

    nested = _json_pointer(payload, "/a~1b")
    first_page = _describe_children(payload, "", offset=0, limit=1)
    assert nested == {"~key": "value"}
    assert first_page["children"] == [{"key": "a/b", "path": "/a~1b", "type": "object"}]
    assert first_page["next_child_offset"] == 1


def test_child_discovery_includes_small_scalar_values() -> None:
    page = _describe_children({"tiny": 7, "large": {"deep": True}, "text": "x"},
        "/obj", offset=0, limit=3)
    children = {item["key"]: item for item in page["children"]}
    assert children["tiny"]["value"] == 7
    assert children["large"]["type"] == "object"
    assert children["text"]["value"] == "x"


def test_mcp_structured_content_keeps_warnings_and_resources_but_drops_duplicate_json() -> None:
    structured = {"ok": True, "items": [1]}
    content = [
        {"type": "text", "text": '{"items":[1],"ok":true}'},
        {"type": "text", "text": "Warning: one item was filtered"},
        {"type": "resource_link", "uri": "file://resource", "name": "details"},
    ]

    retained = _meaningful_mcp_content(content, structured)
    assert retained["items"] == content[1:]
    assert retained["original_count"] == 3
    assert retained["omitted_count"] == 0
    assert retained["truncated"] is False


def test_mcp_content_reports_truncation_and_preserves_late_warning() -> None:
    content = [{"type": "image", "data": "payload"} for _ in range(55)]
    content.append({"type": "text", "text": "Warning: the final page was skipped"})

    retained = _meaningful_mcp_content(content, {})
    assert len(retained["items"]) == 50
    assert retained["omitted_count"] == 6
    assert retained["truncated"] is True
    assert retained["warning_summaries"] == ["Warning: the final page was skipped"]


@pytest.mark.asyncio
async def test_dispatched_write_timeout_is_unknown_but_read_timeout_remains_retryable() -> None:
    target = ProviderExecutionTarget(operation_slug="write", provider_type="mcp",
        provider_instance_id="provider", provider_instance_slug="provider",
        provider_url="http://mcp", data_instance_id="instance", data_instance_slug="instance",
        mcp_tool_name="write")
    write = ResolvedOperation(operation_slug="write", operation="write", name="Write",
        description="write", input_schema={"type": "object", "properties": {}},
        data_instance_id="instance", data_instance_slug="instance", source="mcp",
        target=target, side_effects=True, risk_level="write")
    write_executor = AsyncMock()
    write_executor.execute.side_effect = asyncio.TimeoutError()
    deps = RuntimeDependencies(operation_executor=write_executor)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    ctx.set_runtime_deps(deps)
    result, _ = await ToolExecutor().execute(ToolCall(id="write-1", tool_name="write", arguments={"collection_slug": "instance"}), ctx, [write])
    assert result.metadata["outcome_unknown"] is True
    assert result.metadata["error_code"] == "tool_outcome_unknown"
    assert result.metadata["retryable"] is False

    class FailedExecutor:
        async def execute(self, *_args, **_kwargs):
            return ToolResult.fail("transport failed", retryable=True,
                mcp_failure={"kind": "transport", "category": "availability"})

    failed_executor = FailedExecutor()
    failed_ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    failed_ctx.set_runtime_deps(RuntimeDependencies(operation_executor=failed_executor))
    failed_result, _ = await ToolExecutor().execute(
        ToolCall(id="write-2", tool_name="write", arguments={"collection_slug": "instance"}),
        failed_ctx, [write])
    assert failed_result.metadata["outcome_unknown"] is True
    assert failed_result.metadata["error_code"] == "tool_outcome_unknown"
    assert failed_result.metadata["retryable"] is False

    read = write.model_copy(update={"operation_slug": "read", "operation": "read", "name": "Read",
        "target": target.model_copy(update={"operation_slug": "read", "mcp_tool_name": "read"}),
        "side_effects": False, "risk_level": "safe"})
    read_executor = AsyncMock()
    read_executor.execute.side_effect = asyncio.TimeoutError()
    read_deps = RuntimeDependencies(operation_executor=read_executor)
    read_ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    read_ctx.set_runtime_deps(read_deps)
    read_result, _ = await ToolExecutor().execute(ToolCall(id="read-1", tool_name="read", arguments={"collection_slug": "instance"}), read_ctx, [read])
    assert read_result.metadata["retryable"] is True
    assert "outcome_unknown" not in read_result.metadata
