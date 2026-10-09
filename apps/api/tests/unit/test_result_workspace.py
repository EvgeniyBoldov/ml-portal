"""Regression checks for explicit normalization and dataset presentation."""
import json
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.agents.context import ToolResult, ToolContext
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.tools import OperationExecutionFacade
from app.services.tool_result_protocol import normalize_result
from app.services.tool_result_store import _profile_rows


def test_netbox_page_is_records_with_internal_continuation():
    args = {"object_type": "dcim.device", "filters": {"site": "EVN"}, "limit": 2}
    page = normalize_result({"count": 3, "next": "https://netbox/api/?offset=2&limit=2",
        "results": [{"id": 1}, {"id": 2}]}, "netbox_get_objects", args)
    assert page.value == [{"id": 1}, {"id": 2}]
    assert page.meta.next_arguments == {**args, "offset": 2}
    assert page.meta.total == 3 and not page.meta.complete


def test_jira_page_preserves_nulls_and_filters():
    page = normalize_result({"startAt": 20, "total": 22, "issues": [{"key": "X", "fields": {"assignee": None}}]},
        "jira_search_issues", {"jql": "project=X", "start_at": 20})
    assert page.meta.next_arguments == {"jql": "project=X", "start_at": 21}
    assert page.value[0]["fields"]["assignee"] is None


def test_empty_and_arbitrary_objects_are_not_guessed():
    page = normalize_result({"count": 0, "next": None, "results": []}, "netbox_get_objects", {})
    assert page.value == [] and page.meta.complete
    unknown = {"results": [1], "next": "opaque"}
    page = normalize_result(unknown, "other_api", {})
    assert page.value == [unknown] and page.meta.has_next is None


@pytest.mark.parametrize("value", [None, False, 0, [], ""])
def test_mcp_and_prompt_preserve_falsy_values(value):
    result = DirectOperationExecutor._tool_result_from_payload({"structuredContent": value})
    assert result.success and result.data == value
    assert json.loads(OperationExecutionFacade.format_result_for_context(result)) == value


def test_profile_never_cuts_json_and_describes_heterogeneous_rows():
    rows = [{"id": 1, "name": "x" * 10000}, {"id": 2, "ip": None}]
    schema, sample, _, complete = _profile_rows(rows)
    assert schema["ip"]["missing"] == 1
    assert sample == [] and not complete
    assert _profile_rows([{"id": i} for i in range(10)])[3] is False


def test_stored_descriptor_explains_read_vs_load():
    data = {"result_id": str(uuid4()), "sql_ref": "result_x", "row_count": 50,
            "inline_complete": False, "source_complete": False,
            "dataset_meta": {"has_next": True, "next_arguments": {"secret": "must-not-show"}}}
    view = json.loads(OperationExecutionFacade.format_result_for_context(ToolResult.ok({}), stored_result=data))
    descriptor = view["_runtime_result"]
    assert descriptor["delivery"] == "stored" and descriptor["has_more"]
    assert "result.read" in descriptor["hint"] and "result.load" in descriptor["hint"]
    assert "must-not-show" not in json.dumps(view)


@pytest.mark.asyncio
async def test_local_execution_preserves_runtime_metadata():
    from app.agents.context import ToolCall
    from app.agents.contracts import ProviderExecutionTarget
    expected = ToolResult.ok({"rows": []}, stored_result={"result_id": "saved"})
    registry = type("Registry", (), {"get_handler": lambda self, slug: type("Handler", (), {"execute": AsyncMock(return_value=expected)})()})()
    executor = DirectOperationExecutor(tool_registry=registry)
    target = ProviderExecutionTarget(operation_slug="local", provider_type="local", handler_slug="local",
        data_instance_id="system", data_instance_slug="system")
    executor._resolve_target_binding = lambda *a: (None, target)
    result = await executor.execute(ToolCall(id="call", tool_name="local", arguments={}),
        ToolContext(tenant_id=uuid4(), user_id=uuid4()))
    assert result is expected and result.metadata["stored_result"]["result_id"] == "saved"


def test_reuse_keeps_dataset_identity_instead_of_treating_descriptor_as_source_json():
    from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
    from app.runtime.memory.tool_ledger import ToolLedger
    result_id = str(uuid4())
    ledger = ToolLedger()
    ledger.register_call(operation="source", call_id="first", arguments={}, iteration=1, agent_slug="a", phase_id=None)
    ledger.register_result(call_id="first", success=True, data={"row_count": 50}, result_id=result_id)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={"runtime_tool_ledger": ledger})
    result, _ = ToolCallReusePolicy().maybe_reuse(operation_slug="source", arguments={}, ctx=ctx)
    assert result.metadata["stored_result"]["result_id"] == result_id
    assert not result.metadata["stored_result"]["inline_complete"]


def test_sql_mcp_adapter_extracts_rows_and_retains_truncation():
    rows = [{"count": 50000}]
    complete = normalize_result({"rows": rows, "columns": ["count"], "truncated": False}, "execute_sql", {})
    partial = normalize_result({"rows": rows, "columns": ["count"], "truncated": True}, "execute_sql", {})
    assert complete.value == rows and complete.meta.complete
    assert partial.value == rows and not partial.meta.complete and partial.meta.total is None


def test_invalid_source_protocol_returns_workspace_error():
    from app.services.result_workspace import normalized_page
    from app.services.tool_result_store import ToolResultStoreError
    with pytest.raises(ToolResultStoreError, match="protocol is invalid"):
        normalized_page({"results": None}, "netbox_get_objects", {})


def test_sql_projection_keeps_literal_json_keys_and_omits_ambiguous_paths():
    from app.services.result_sql_projection import sql_columns
    schema, *_ = _profile_rows([{"a.b": 1}])
    assert sql_columns(schema)["a.b"]["path"] == ["a.b"]
    schema, *_ = _profile_rows([{"a.b": 1, "a": {"b": 2}}])
    assert sql_columns(schema)["a.b"]["path"] == ["a.b"]
    assert sql_columns(schema)["a"]["type"] == "jsonb"


def test_column_names_are_stable_after_jsonb_reorders_schema_keys():
    from app.services.result_sql_projection import sql_columns
    schema, *_ = _profile_rows([{"a-b": 1, "a_b": 2, "ordinal": 3, "data": 4,
                                "device_type": {"display": "Router"}, "empty": None}])
    columns = sql_columns(schema)
    assert columns == sql_columns(dict(reversed(list(schema.items()))))
    assert columns["device_type"]["type"] == "jsonb"
    assert columns["empty"]["type"] == "jsonb"
    assert columns["data"]["path"] == ["data"] and columns["ordinal"]["path"] == ["ordinal"]
    assert {tuple(column["path"]) for column in columns.values()} >= {("data",), ("ordinal",)}


def test_netbox_rejects_nonadvancing_continuation_and_inconsistent_protocol():
    with pytest.raises(ValueError, match="advance"):
        normalize_result({"count": 2, "results": [{"id": 1}], "next": "https://netbox/?offset=0"},
                         "netbox_get_objects", {"offset": 0})
    with pytest.raises(ValueError, match="complete"):
        normalize_result({"value": [{"id": 1}], "meta": {"total": 2, "has_next": True, "complete": True}},
                         "netbox_get_objects", {})
    unknown = normalize_result({"results": [{"id": 1}]}, "netbox_get_objects", {})
    assert unknown.meta.complete is None and unknown.meta.has_next is None


def test_model_descriptor_exposes_exact_columns_and_schema_continuation():
    from app.services.result_sql_projection import sql_columns
    rows = [{f"field_{index}": index for index in range(100)}]
    schema, *_ = _profile_rows(rows)
    saved = {"result_id": str(uuid4()), "sql_ref": "result_example", "row_count": 1,
             "observed_schema": schema, "schema_complete": True, "inline_complete": False,
             "source_complete": True, "dataset_meta": {"has_next": False, "complete": True}}
    rendered = OperationExecutionFacade.format_result_for_context(ToolResult.ok(rows), stored_result=saved)
    descriptor = json.loads(rendered)["_runtime_result"]
    assert len(rendered.encode()) <= 4000
    assert descriptor["schema_total_columns"] == len(sql_columns(schema))
    assert descriptor["schema_returned_columns"] == len(descriptor["sql_columns"])
    assert descriptor["next_schema_offset"] == len(descriptor["sql_columns"])
    assert not descriptor["schema_page_complete"]
    assert descriptor["schema_complete"]  # Profiling completeness differs from delivery completeness.
    for name, column in descriptor["sql_columns"].items():
        assert column == sql_columns(schema)[name]


def test_virtual_columns_stay_top_level_and_search_accepts_multiple_fields():
    from app.services.result_sql_projection import schema_page, sql_columns
    schema, *_ = _profile_rows([{"name": "a", "device_type": {"model": "r1"}, "tags": [1]},
                                {"name": "b", "optional": 1, "mixed": "x"}, {"mixed": 2}])
    columns = sql_columns(schema)
    assert columns["device_type"]["type"] == columns["tags"]["type"] == columns["mixed"]["type"] == "jsonb"
    assert set(columns) == {"name", "device_type", "tags", "optional", "mixed"}
    page = schema_page(schema, query="name, device_type")
    assert set(page["sql_columns"]) == {"name", "device_type"}
    assert page["schema_total_columns"] == 5 and page["schema_matched_columns"] == 2
    assert "sql_base_columns" not in page


def test_literal_special_keys_are_columns_without_internal_root_metadata():
    from app.services.result_sql_projection import sql_columns
    schema, *_ = _profile_rows([{"$": 1, "*": 2, "a.b": 3}])
    assert set(sql_columns(schema)) == {"$", "*", "a.b"}
    assert sql_columns(schema)["$"]["path"] == ["$"]


def test_sql_guard_resolves_cte_scopes_and_rejects_external_functions():
    from app.services.result_sql_guard import referenced_results
    assert referenced_results("WITH items AS (SELECT * FROM RESULT_X) SELECT count(*) FROM items", {"result_x"}) == {"result_x"}
    for sql in ("SELECT pg_read_file('/etc/passwd')", "SELECT * FROM read_csv('/etc/passwd')",
                "SELECT custom.to_jsonb('x')",
                "WITH items AS (SELECT * FROM runtime_tool_payloads) SELECT * FROM items",
                "WITH a AS (SELECT * FROM b), b AS (SELECT 1) SELECT * FROM a",
                "SELECT 1; SELECT 2"):
        with pytest.raises(ValueError):
            referenced_results(sql, {"result_x"})


def test_small_inline_result_keeps_all_columns_before_sample():
    row = {"id": 1, "name": "r1", "status": {"label": "Active", "value": "active"},
           "device_type": {"model": "router"}, "tags": [], "ip": None}
    schema, sample, *_ = _profile_rows([row])
    saved = {"result_id": str(uuid4()), "sql_ref": "result_mock", "call_id": "call",
             "row_count": 1, "inline_complete": True, "source_complete": True,
             "observed_schema": schema, "sample": sample, "dataset_meta": {"complete": True, "has_next": False}}
    view = json.loads(OperationExecutionFacade.format_result_for_context(ToolResult.ok({"value": [row]}), stored_result=saved))
    meta = view["_runtime_result"]
    assert set(meta["sql_columns"]) == set(row)
    assert meta["schema_page_complete"] and not meta["schema_entry_too_large"]
    assert "sample" not in meta  # Inline records are already present; no duplicate competing with schema.
    assert "result.read" in meta["hint"] and "->>" in meta["hint"]


def test_search_adapter_extracts_rows_and_retains_partial_errors():
    args = {"q": "router", "object_types": ["dcim.device", "dcim.site"], "limit": 1}
    raw = {"results": [{"object_type": "dcim.device", "count": 2,
                       "next": "https://netbox/?offset=1&limit=1", "results": [{"name": "router", "status": {"value": "active"}}]}],
           "errors": [{"object_type": "dcim.site", "status": 403}], "searched_types": args["object_types"]}
    page = normalize_result(raw, "netbox_search_objects", args)
    assert page.value == raw["results"][0]["results"]
    assert page.meta.complete is False and page.meta.total is None
    assert page.meta.next_arguments == {**args, "offset": 1}
    assert page.meta.model_dump()["errors"] == raw["errors"]
    assert page.meta.model_dump()["coverage_incomplete"]


def test_empty_search_is_zero_records_with_known_coverage():
    page = normalize_result({"results": [{"object_type": "dcim.device", "results": [], "count": 0, "next": None}],
        "errors": [], "searched_types": ["dcim.device"]}, "netbox_search_objects", {"q": "none"})
    assert page.value == [] and page.meta.total == 0 and page.meta.complete
