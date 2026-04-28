from __future__ import annotations

from app.runtime.memory.tool_ledger import ToolLedger


def test_tool_ledger_marks_duplicate_call_after_completed_match():
    ledger = ToolLedger()

    ledger.register_call(
        operation="collection.sql.execute",
        call_id="c1",
        arguments={"query": "select 1"},
        iteration=1,
        agent_slug="mon.net",
        phase_id="p1",
    )
    ledger.register_result(call_id="c1", success=True, data={"rows": [1]})

    second = ledger.register_call(
        operation="collection.sql.execute",
        call_id="c2",
        arguments={"query": "select 1"},
        iteration=2,
        agent_slug="mon.net",
        phase_id="p1",
    )

    assert second.duplicate_of_call_id == "c1"


def test_tool_ledger_compact_view_contains_status_and_preview():
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.table.search",
        call_id="c1",
        arguments={"where": {"id": 1}},
        iteration=1,
        agent_slug="agent.a",
        phase_id=None,
    )
    ledger.register_result(call_id="c1", success=False, data="not found")

    view = ledger.compact_view(max_items=3)
    assert len(view) == 1
    assert view[0]["call_id"] == "c1"
    assert view[0]["status"] == "failed"
    assert view[0]["success"] is False
    assert view[0]["args_preview"]


def test_tool_ledger_find_successful_result_by_signature():
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.sql.execute",
        call_id="c1",
        arguments={"query": "select 1"},
        iteration=1,
        agent_slug="a",
        phase_id=None,
    )
    ledger.register_result(call_id="c1", success=True, data={"rows": [1]})

    found = ledger.find_successful_result(
        operation="collection.sql.execute",
        arguments={"query": "select 1"},
    )
    assert found is not None
    assert found.call_id == "c1"
    assert found.result_data == {"rows": [1]}
