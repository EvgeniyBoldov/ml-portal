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

    result = await ResultAnalyzeTool().execute(ctx, {"result_id": "result-1", "mode": "overview"}, version="1.1.0")

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

    result = await ResultAnalyzeTool().execute(ctx, {"result_id": "result-1", "mode": "project", "paths": paths}, version="1.1.0")

    assert result.success
    assert result.data["values"]["fields.status.name"] == "Open"
    assert analyze.await_args.kwargs["paths"] == paths
    assert ResultAnalyzeTool().get_latest_version().version == "2.0.0"


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


def test_sql_result_names_and_generic_dataset_profiles() -> None:
    from decimal import Decimal
    from app.services.tool_result_store import _dataset_rows, _json_compatible, _profile_rows, sql_ref_for_result

    result_id = "a81f0000-0000-4000-8000-000000000001"
    assert sql_ref_for_result(result_id) == "result_a81f0000000040008000000000000001"
    rows = _dataset_rows([{"key": "OPS-1", "fields": {"state": None}}, {"key": "OPS-2"}])
    schema, sample, schema_complete, sample_complete = _profile_rows(rows)
    assert schema["key"]["present"] == 2
    assert schema["fields"]["types"] == ["object"]
    assert schema["fields"]["missing"] == 1
    assert "fields.state" not in schema
    assert sample == rows
    assert schema_complete and sample_complete

    wrapper = {"total": 2, "results": [{"id": 1}, {"id": 2}]}
    assert _dataset_rows(wrapper) == [wrapper]
    assert _json_compatible({"count": Decimal("2"), "ratio": Decimal("1.25")}) == {"count": 2, "ratio": 1.25}


@pytest.mark.asyncio
async def test_sql_query_uses_exact_saved_result_names_and_persists_output(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.tool_result_store import sql_ref_for_result

    source_id = "a81f0000-0000-4000-8000-000000000001"
    saved = {
        "result_id": "b92f0000-0000-4000-8000-000000000002",
        "sql_ref": sql_ref_for_result("b92f0000-0000-4000-8000-000000000002"),
        "row_count": 1, "observed_schema": {"$": {"types": ["object"]}},
        "sample": {"count": 1}, "schema_complete": True,
        "sample_complete": True, "inline_complete": True,
    }
    store = ToolResultStore()
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[{
        "result_id": source_id, "sql_ref": sql_ref_for_result(source_id),
        "source_complete": True,
    }, {
        "result_id": "c03f0000-0000-4000-8000-000000000003",
        "sql_ref": sql_ref_for_result("c03f0000-0000-4000-8000-000000000003"),
        "source_complete": False,
    }]))
    save = AsyncMock(return_value=saved)
    monkeypatch.setattr(store, "save", save)

    class FakeQueryResult:
        def mappings(self) -> FakeQueryResult:
            return self

        def __iter__(self):
            return iter([{"count": 1}])

    class FakeConnection:
        def __init__(self) -> None:
            self.query = ""
            self.params = {}

        async def execute(self, statement: object, params: dict | None = None) -> FakeQueryResult:
            rendered = str(statement)
            if "_agent_query AS" in rendered:
                self.query = rendered
                self.params = params or {}
            return FakeQueryResult()

    connection = FakeConnection()

    class ConnectionManager:
        async def __aenter__(self) -> FakeConnection:
            return connection

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeEngine:
        def begin(self) -> ConnectionManager:
            return ConnectionManager()

    monkeypatch.setattr("app.services.tool_result_store.get_tool_results_engine", lambda: FakeEngine())
    source_ref = sql_ref_for_result(source_id)
    result = await store.execute_sql(
        sql=f"SELECT count(*) FROM {source_ref}", run_id="run-1",
        tenant_id=uuid4(), user_id=uuid4(), call_id="call-2",
        task_id="task-1", agent_execution_id="agent-1",
    )

    assert f"{source_ref} AS (SELECT " in connection.query
    assert "SELECT ordinal, data" not in connection.query
    assert f"FROM {source_ref}" in connection.query
    assert connection.params["source_id_0"] == source_id
    assert result["sql_ref"] == saved["sql_ref"]
    assert result["rows"] == [{"count": 1}]
    assert save.await_args.kwargs["operation"] == "result.analyze.sql"
    assert save.await_args.kwargs["source_result_ids"] == [source_id]
    assert save.await_args.kwargs["source_complete"] is True
    assert result["source_complete"] is True
    assert result["query_complete"] is True
    assert result["source_count"] == 1
    assert result["source_result_ids"] == [source_id]


def test_sql_provenance_ignores_literals_and_nested_comments():
    from app.services.result_sql_guard import referenced_results

    sql = """SELECT 'result_old', $$result_old$$, $tag$result_old$tag$
             FROM "result_new" -- result_old
             /* outer /* result_old */ result_old */
             JOIN result_other ON true"""
    tokens = referenced_results(sql, {"result_new", "result_other"})
    assert "result_old" not in tokens
    assert {"result_new", "result_other"}.issubset(tokens)


@pytest.mark.asyncio
async def test_result_analyze_v2_persists_query_result_and_returns_catalog_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    result_id = "b92f0000-0000-4000-8000-000000000002"
    execute_sql = AsyncMock(return_value={
        "mode": "sql", "result_id": result_id,
        "sql_ref": "result_b92f0000000040008000000000000002",
        "row_count": 1, "rows": [{"count": 1}],
        "_stored_result": {"result_id": result_id},
    })
    monkeypatch.setattr(ToolResultStore, "execute_sql", execute_sql)
    ctx = ToolContext(
        tenant_id=uuid4(), user_id=uuid4(),
        extra={"runtime_root_run_id": "run-1", "runtime_active_tool_call_id": "call-1"},
    )

    result = await ResultAnalyzeTool().execute(ctx, {"sql": "SELECT 1 AS count"})

    assert result.success
    assert result.data["sql_ref"] == "result_b92f0000000040008000000000000002"
    assert result.metadata["stored_result"]["result_id"] == result_id
    assert execute_sql.await_args.kwargs["run_id"] == "run-1"
    assert execute_sql.await_args.kwargs["call_id"] == "call-1"


def test_explicit_null_filter_is_preserved_by_argument_normalization() -> None:
    schema = ResultAnalyzeTool().get_version("1.1.0").input_schema
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
        }, version="1.1.0")
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
