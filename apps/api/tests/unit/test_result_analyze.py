from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.result_analyze import ResultAnalyzeTool
from app.agents.context import ToolContext
from app.agents.runtime.tools import OperationExecutionFacade
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError, _source_complete, _source_total


@pytest.mark.asyncio
async def test_result_analyze_uses_tool_context_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    analyze = AsyncMock(return_value={"result_id": "result-1", "mode": "overview", "fields": []})
    monkeypatch.setattr(ToolResultStore, "analyze", analyze)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={"runtime_root_run_id": "run-1"})

    result = await ResultAnalyzeTool().execute(ctx, {"result_id": "result-1", "mode": "overview"})

    assert result.success
    assert result.metadata["logs"][0]["message"] == "result_analyzed"
    assert analyze.await_args.kwargs["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_result_analyze_projects_object_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    analyze = AsyncMock(return_value={
        "result_id": "result-1", "mode": "project", "values": {
            "key": "NIMS-2712", "fields.summary": "Example", "fields.status.name": "Open",
        }, "missing_paths": [], "source_complete": True,
    })
    monkeypatch.setattr(ToolResultStore, "analyze", analyze)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={"runtime_root_run_id": "run-1"})
    paths = ["key", "fields.summary", "fields.status.name"]

    result = await ResultAnalyzeTool().execute(ctx, {"result_id": "result-1", "mode": "project", "paths": paths})

    assert result.success
    assert result.data["values"]["fields.status.name"] == "Open"
    assert analyze.await_args.kwargs["paths"] == paths
    assert ResultAnalyzeTool().get_latest_version().version == "1.1.0"


def test_nested_jira_comment_pagination_is_not_complete() -> None:
    issue = {"key": "NIMS-2712", "fields": {"comment": {
        "startAt": 0, "total": 3, "comments": [{"id": "1"}],
    }}}
    assert not _source_complete(issue)
    issue["fields"]["comment"]["comments"].extend([{"id": "2"}, {"id": "3"}])
    assert _source_complete(issue)
    issue["fields"]["comment"]["startAt"] = 1
    assert not _source_complete(issue)
    issue["fields"]["comment"]["startAt"] = "unexpected"
    assert not _source_complete(issue)


def test_netbox_count_and_pagination_mark_partial_results() -> None:
    page = {"count": 3, "next": "page-2", "previous": None, "results": [{"id": 1}]}
    assert _source_total(page) == 3
    assert not _source_complete(page)
    page["next"] = None
    assert not _source_complete(page)
    page["results"] = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert _source_complete(page)
    page["previous"] = "page-1"
    assert not _source_complete(page)


def test_explicit_null_filter_is_preserved_by_argument_normalization() -> None:
    schema = ResultAnalyzeTool().get_latest_version().input_schema
    arguments = {"filter_path": "status", "equals": None, "offset": None}
    assert OperationExecutionFacade._strip_optional_nulls(arguments, schema) == {
        "filter_path": "status", "equals": None,
    }


@pytest.mark.asyncio
async def test_explicit_null_and_false_filters_remain_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    analyze = AsyncMock(return_value={"result_id": "result-1", "mode": "aggregate", "count": 0})
    monkeypatch.setattr(ToolResultStore, "analyze", analyze)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={"runtime_root_run_id": "run-1"})
    tool = ResultAnalyzeTool()
    for value in (None, "", False, 0):
        result = await tool.execute(ctx, {
            "result_id": "result-1", "mode": "aggregate", "array_path": "results",
            "filter_path": "status", "equals": value,
        })
        assert result.success
        assert analyze.await_args.kwargs["equals_provided"] is True
        assert analyze.await_args.kwargs["equals"] is value


@pytest.mark.asyncio
async def test_project_rejects_arrays_and_missing_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ToolResultStore()
    with pytest.raises(ToolResultStoreError, match="paths is required"):
        await store.analyze(
            result_id="result-1", run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            mode="project", paths=[],
        )


@pytest.mark.asyncio
async def test_project_reads_bounded_nested_values_with_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResult:
        def __init__(self, item: dict) -> None:
            self.item = item

        def mappings(self) -> FakeResult:
            return self

        def first(self) -> dict:
            return self.item

    class FakeConnection:
        async def execute(self, statement: object, args: dict) -> FakeResult:
            assert "tenant_id = :tenant_id AND user_id = :user_id" in str(statement)
            path = ".".join(args["path"])
            data = {
                "key": {"value_type": "string", "value": "NIMS-2712"},
                "fields.status.name": {"value_type": "string", "value": "Open"},
                "fields.description": {"value_type": "null", "value": None},
                "fields.unknown": {"value_type": None, "value": None},
                "fields.subtasks": {"value_type": "array", "value": []},
            }
            return FakeResult(data[path])

    class FakeConnectionManager:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEngine:
        def connect(self) -> FakeConnectionManager:
            return FakeConnectionManager()

    monkeypatch.setattr("app.services.tool_result_store.get_tool_results_engine", lambda: FakeEngine())
    store = ToolResultStore()
    tenant_id, user_id = uuid4(), uuid4()
    result = await store._project(
        "result-1", "run-1", tenant_id, user_id,
        ["key", "fields.status.name", "fields.description", "fields.unknown"],
        {"source_complete": True},
    )
    assert result["values"] == {
        "key": "NIMS-2712", "fields.status.name": "Open", "fields.description": None,
    }
    assert result["missing_paths"] == ["fields.unknown"]
    with pytest.raises(ToolResultStoreError, match="use select"):
        await store._project(
            "result-1", "run-1", tenant_id, user_id, ["fields.subtasks"],
            {"source_complete": True},
        )


@pytest.mark.asyncio
async def test_text_reads_long_field_by_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResult:
        def mappings(self) -> FakeResult:
            return self

        def first(self) -> dict:
            return {"value_type": "string", "text_length": 3000, "chunk": "sample"}

    class FakeConnection:
        async def execute(self, statement: object, args: dict) -> FakeResult:
            assert args["path"] == ["fields", "description"]
            assert args["start"] == 1501
            assert args["limit"] == 1000
            assert "tenant_id = :tenant_id AND user_id = :user_id" in str(statement)
            return FakeResult()

    class FakeConnectionManager:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEngine:
        def connect(self) -> FakeConnectionManager:
            return FakeConnectionManager()

    monkeypatch.setattr("app.services.tool_result_store.get_tool_results_engine", lambda: FakeEngine())
    result = await ToolResultStore()._text(
        "result-1", "run-1", uuid4(), uuid4(), "fields.description", 1500, 1000,
        {"source_complete": True},
    )
    assert result["chunk"] == "sample"
    assert result["next_offset"] == 1506
    assert result["complete"] is False
