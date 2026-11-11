import json

from app.agents.runtime.model_context import (
    observe_no_progress_batch, outbound_request_snapshot, project_model_messages, runtime_result_metadata,
    reallocate_result_batch, model_result_inline_complete, update_result_inline_coverage,
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


def test_batch_reallocation_is_order_independent_when_large_and_small_both_fit():
    from app.adapters.impl.llm_context import estimate_request_tokens

    def render(item, budget):
        full = item["full"]
        return full if estimate_request_tokens({"model": "gpt-4o-mini", "messages": [
            {"role": "tool", "content": full}]}) <= budget else item["minimum_receipt"]

    def request(texts):
        return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "|".join(texts)}],
                "tools": [{"type": "function", "function": {"name": "result.read",
                    "parameters": {"type": "object", "properties": {"result_id": {"type": "string"}}}}}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "schema": {"type": "object", "properties": {"status": {"type": "string"}}}}}}

    large = {"call_id": "large", "minimum_receipt": '{"status":"stored","result_id":"r-large"}',
             "full": "large evidence " * 40}
    small = {"call_id": "small", "minimum_receipt": '{"status":"stored","result_id":"r-small"}',
             "full": "small evidence"}
    for items in ([large, small], [small, large]):
        allocation = reallocate_result_batch(items, total_budget_tokens=512, model="gpt-4o-mini",
            format_item=render, request_for_texts=request, context_window_tokens=8192)
        assert allocation.fits_request
        assert allocation.full_candidate_selected == [True, True]
        assert len(allocation.texts) == 2


def test_batch_reallocation_reverts_to_receipts_when_full_request_reserve_fails():
    def render(item, budget):
        return item["full"] if budget > 100 else item["minimum_receipt"]

    items = [{"call_id": "a", "minimum_receipt": '{"status":"stored","result_id":"a"}',
              "full": "x" * 5_000}]
    allocation = reallocate_result_batch(items, total_budget_tokens=1_000, model="gpt-4o-mini",
        format_item=render, request_for_texts=lambda texts: {"model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "fixed request " * 20_000 + texts[0]}],
            "tools": [{"type": "function", "function": {"name": "result.read",
                "parameters": {"type": "object", "properties": {"result_id": {"type": "string"}}}}}],
            "response_format": {"type": "json_schema", "json_schema": {"schema": {"type": "object"}}}},
        context_window_tokens=2_048)
    assert not allocation.fits_request
    assert allocation.texts == [items[0]["minimum_receipt"]]


def test_downgraded_final_receipt_updates_existing_ledger_completeness_without_new_result():
    from app.runtime.memory.tool_ledger import ToolLedger

    ledger = ToolLedger()
    entry = ledger.register_call(operation="result.read", call_id="read-1", arguments={},
        iteration=1, agent_slug="reader", phase_id="task")
    ledger.register_result(call_id="read-1", success=True, data={"records": [{"id": 1}]},
        result_id="result-1", result_inline_complete=True, result_source_complete=True,
        result_delivery="stored")
    original_fingerprint = entry.result_fingerprint
    final_text = json.dumps({"status": "ready", "result_id": "result-1", "revision": 1,
                             "next_action": {"tool": "result.read"}})
    complete = model_result_inline_complete(final_text, stored_result={"result_id": "result-1"},
                                            result_success=True)
    update_result_inline_coverage(ledger, call_id="read-1", inline_complete=complete)
    assert entry.result_inline_complete is False
    assert entry.result_fingerprint == original_fingerprint
    assert entry.stored_result_id == "result-1"
    assert len(ledger.entries) == 1


def test_batch_reallocates_real_direct_and_stored_tool_views_without_calling_tools():
    from types import SimpleNamespace
    from app.adapters.impl.llm_context import estimate_request_tokens
    from app.agents.context import ToolCall, ToolResult
    from app.agents.runtime.tools import OperationExecutionFacade
    from app.agents.protocol import build_tool_result_messages

    large_call = ToolCall(id="stored-large", tool_name="result.read", arguments={})
    small_call = ToolCall(id="direct-small", tool_name="memory.search", arguments={})
    entries = [
        {"call": large_call, "call_id": large_call.id,
         "result": ToolResult.ok({"result_id": "r-large", "value": [{"text": "stored fact " * 80}],
                                  "loaded_items": 1, "source_complete": True}, workspace_view=True),
         "stored_result": {"result_id": "r-large", "revision": 1, "source_complete": True,
                           "row_count": 1}, "evidence_call_id": large_call.id},
        {"call": small_call, "call_id": small_call.id,
         "result": ToolResult.ok({"items": [{"text": "direct fact"}]}, delivery="direct"),
         "stored_result": None, "evidence_call_id": small_call.id},
    ]

    def formatter(entry, budget):
        if budget == 0 and entry["result"].delivery == "direct":
            return entry["minimum_receipt"]
        return OperationExecutionFacade.format_result_for_context(
            entry["result"], operation_slug=entry["call"].tool_name,
            evidence_call_id=entry["evidence_call_id"], stored_result=entry["stored_result"],
            context_budget_tokens=budget, context_model="gpt-4o-mini")

    for ordered in (entries, list(reversed(entries))):
        for item in ordered:
            if item["result"].delivery == "direct":
                item["minimum_receipt"] = json.dumps({"status": "unavailable", "reason": "batch_context_budget",
                    "operation": item["call"].tool_name, "evidence_call_id": item["call_id"],
                    "recoverability": "not_stored"})
        full = [formatter(item, 2_000) for item in ordered]
        total = sum(estimate_request_tokens({"model": "gpt-4o-mini", "messages": [
            {"role": "tool", "content": content}]}) for content in full) + 40
        raw_calls = [{"id": item["call"].id, "function": {"name": item["call"].tool_name}}
                     for item in ordered]

        def request(texts):
            tool_results = build_tool_result_messages(
                [(item["call"], content) for item, content in zip(ordered, texts)], raw_calls)
            return {"model": "gpt-4o-mini", "messages": [
                {"role": "assistant", "tool_calls": raw_calls}, *tool_results]}

        allocation = reallocate_result_batch(ordered, total_budget_tokens=total,
            model="gpt-4o-mini", format_item=formatter, request_for_texts=request,
            context_window_tokens=8192)
        assert allocation.fits_request
        assert all(allocation.full_candidate_selected)
        assert [message["tool_call_id"] for message in request(allocation.texts)["messages"][1:]] == [
            item["call"].id for item in ordered]


def test_batch_reallocation_uses_leftover_for_bounded_partial_candidate():
    from app.adapters.impl.llm_context import estimate_request_tokens
    minimum = '{"status":"stored","result_id":"r"}'
    items = [
        {"call_id": "large", "minimum_receipt": minimum, "full": "L " * 200},
        {"call_id": "small", "minimum_receipt": minimum, "full": "S " * 8},
    ]

    def render(item, budget):
        if item["call_id"] == "small":
            return item["full"] if estimate_request_tokens({"messages": [
                {"role": "tool", "content": item["full"]}]}) <= budget else item["minimum_receipt"]
        if budget >= 25:
            return "bounded page " * 8
        return item["minimum_receipt"]

    allocation = reallocate_result_batch(items, total_budget_tokens=70, model="gpt-4o-mini",
        format_item=render, request_for_texts=lambda texts: {"model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "|".join(texts)}]}, context_window_tokens=8192)
    assert allocation.fits_request
    assert allocation.texts[0] != minimum
    assert allocation.texts[1] == items[1]["full"]


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


def test_outbound_snapshot_is_exact_estimation_and_provider_request_shape():
    from app.adapters.impl.llm_context import estimate_request_tokens

    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "ask"}]
    tools = [{"type": "function", "function": {"name": "search", "parameters": {"type": "object"}}}]
    snapshot = outbound_request_snapshot(model="provider/model", messages=messages,
        tools=tools, tool_choice="required", response_format=None)
    assert snapshot == {"model": "provider/model", "messages": messages,
                       "tools": tools, "tool_choice": "required"}
    assert estimate_request_tokens(snapshot) == estimate_request_tokens({
        "model": "provider/model", "messages": messages, "tools": tools,
        "tool_choice": "required"})
    messages[1]["content"] = "changed"
    assert snapshot["messages"][1]["content"] == "ask"
