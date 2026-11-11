import json

from app.agents.runtime.model_context import (
    observe_no_progress_batch, project_model_messages, runtime_result_metadata,
)


def test_model_projection_compacts_old_tool_receipts_but_keeps_current_native_pair():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "old", "type": "function"}]},
        {"role": "tool", "tool_call_id": "old", "content": json.dumps({
            "_runtime_result": {"result_id": "r1", "revision": 2, "schema": {"huge": "x"}},
            "receipt": "x" * 2000, "data": {"rows": [1, 2]},
        })},
        {"role": "assistant", "tool_calls": [{"id": "new", "type": "function"}]},
        {"role": "tool", "tool_call_id": "new", "content": '{"data":"fresh evidence"}'},
    ]
    projected = project_model_messages(messages)
    old = json.loads(projected[1]["content"])
    assert old["_runtime_result"] == {"result_id": "r1", "revision": 2}
    assert "data" not in old
    assert projected[3]["content"] == messages[3]["content"]
    assert messages[1]["content"] != projected[1]["content"]
    assert [m.get("tool_call_id") for m in projected if m["role"] == "tool"] == ["old", "new"]


def test_projection_never_drops_unrecoverable_direct_evidence():
    direct = json.dumps({"facts": "important direct evidence " * 200})
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "old", "type": "function"}]},
        {"role": "tool", "tool_call_id": "old", "content": direct},
        {"role": "assistant", "tool_calls": [{"id": "new", "type": "function"}]},
    ]
    assert project_model_messages(messages)[1]["content"] == direct


def test_projection_compacts_confirmed_saved_result_receipt_without_repeating_schema():
    saved = json.dumps({"status": "ready", "result_id": "r-1", "revision": 4,
                        "records": [{"private": "payload"} for _ in range(100)],
                        "schema": {"repeated": "schema"}})
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "old", "type": "function"}]},
        {"role": "tool", "tool_call_id": "old", "content": saved},
        {"role": "assistant", "tool_calls": [{"id": "new", "type": "function"}]},
    ]
    compacted = json.loads(project_model_messages(messages)[1]["content"])
    assert compacted["result_id"] == "r-1" and compacted["revision"] == 4
    assert "records" not in compacted and "schema" not in compacted


def test_projection_keeps_older_read_facts_even_when_they_reference_a_saved_result():
    receipt = json.dumps({"status": "ready", "result_id": "r-1", "revision": 4,
                          "records": [{"fact": "keep"} for _ in range(100)]})
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "read", "type": "function",
            "function": {"name": "result.read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "read", "content": receipt},
        {"role": "assistant", "tool_calls": [{"id": "new", "type": "function",
            "function": {"name": "api.search", "arguments": "{}"}}]},
    ]
    assert project_model_messages(messages)[1]["content"] == receipt


def test_result_metadata_reads_compact_delivery_and_preserves_explicit_false():
    assert runtime_result_metadata(json.dumps({"_runtime_result": {
        "result_id": "r1", "inline_complete": False, "source_complete": False,
        "revision": 3, "schema": {"columns": [], "next_schema_offset": 8},
    }})) == {
        "result_id": "r1", "inline_complete": False, "source_complete": False,
        "revision": 3, "schema": {"columns": [], "next_schema_offset": 8},
    }
    assert runtime_result_metadata('{"status":"ready","result_id":"r2","records":[]}')["inline_complete"] is True


def test_no_progress_only_counts_identical_reused_or_blocked_batches():
    from types import SimpleNamespace
    state = {}
    call = SimpleNamespace(tool_name="collection.search", arguments={"query": "same"})
    assert observe_no_progress_batch(state, [call], [{"success": True, "reused": True}], threshold=3) == (True, False)
    assert observe_no_progress_batch(state, [call], [{"success": True, "reused": True}], threshold=3) == (True, False)
    assert observe_no_progress_batch(state, [call], [{"success": True, "reused": True}], threshold=3) == (True, True)
    assert observe_no_progress_batch(state, [call], [{"success": False, "error_code": "operation_execution_failed"}], threshold=3) == (False, False)
    assert observe_no_progress_batch(state, [call], [{"success": False, "error_code": "duplicate_execution_blocked"}], threshold=3) == (True, False)


def test_model_inventory_omits_repeated_schema_without_changing_catalog():
    from app.agents.runtime.model_context import project_datastore
    catalog = {"results_status": "available", "items": [{
        "kind": "result", "result_id": "r1", "revision": 3, "row_count": 2,
        "source_complete": False, "sql_columns": {"name": {"type": "text"}},
        "producer": {"task_id": "task"},
    }, {"kind": "file", "artifact_id": "file1"}]}
    view = project_datastore(catalog)
    assert view["items"][0] == {"kind": "result", "result_id": "r1", "revision": 3,
                                 "row_count": 2, "source_complete": False}
    assert "sql_columns" in catalog["items"][0]
    assert view["items"][1] == catalog["items"][1]
