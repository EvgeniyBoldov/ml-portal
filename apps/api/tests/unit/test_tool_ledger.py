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
    ledger.register_result(
        call_id="c1", success=True, data={"rows": [1]},
        sources=[{"url": "https://example.test/result"}],
    )

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
    ledger.register_result(
        call_id="c1", success=True, data={"rows": [1]},
        sources=[{"url": "https://example.test/result"}],
    )

    found = ledger.find_successful_result(
        operation="collection.sql.execute",
        arguments={"query": "select 1"},
    )
    assert found is not None
    assert found.call_id == "c1"
    assert found.result_data == {"rows": [1]}
    assert found.sources == [{"url": "https://example.test/result"}]


def test_tool_ledger_reuse_is_scoped_to_phase():
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.sql.execute", call_id="c1", arguments={"query": "select 1"},
        iteration=1, agent_slug="a", phase_id="task-a",
    )
    ledger.register_result(call_id="c1", success=True, data={"rows": [1]})

    assert ledger.find_successful_result(
        operation="collection.sql.execute", arguments={"query": "select 1"}, phase_id="task-b",
    ) is None


def test_tool_ledger_reuse_matches_resolved_target_and_can_ignore_cache_ttl():
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.sql.execute", call_id="c1", arguments={"query": "select 1"},
        iteration=1, agent_slug="a", phase_id="execution-a", target_identity="provider-a/db-a",
    )
    ledger.register_result(call_id="c1", success=True, data={"rows": [1]})

    assert ledger.find_successful_result(
        operation="collection.sql.execute", arguments={"query": "select 1"},
        phase_id="execution-a", target_identity="provider-b/db-a", max_age_seconds=None,
    ) is None
    found = ledger.find_successful_result(
        operation="collection.sql.execute", arguments={"query": "select 1"},
        phase_id="execution-a", target_identity="provider-a/db-a", max_age_seconds=None,
    )
    assert found is not None and found.call_id == "c1"


def test_tool_ledger_exposes_unresolved_matching_attempt_to_execution_guard():
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.sql.execute", call_id="c1", arguments={"query": "select 1"},
        iteration=1, agent_slug="a", phase_id="execution-a", target_identity="provider-a/db-a",
    )
    assert ledger.find_execution_guard(
        operation="collection.sql.execute", arguments={"query": "select 1"},
        phase_id="execution-a", target_identity="provider-a/db-a",
    ).call_id == "c1"


def test_tool_ledger_preserves_duplicate_status_when_large_result_is_not_cached():
    ledger = ToolLedger()
    ledger.register_call(operation="collection.sql.execute", call_id="c1", arguments={"query": "select 1"},
                         iteration=1, agent_slug="a", phase_id="task-a", target_identity="db")
    ledger.set_call_target(call_id="c1", target_identity="db", execution_id="exec-a")
    ledger.register_result(call_id="c1", success=True, data={"payload": "x" * 25_000})
    prior = ledger.find_successful_result(operation="collection.sql.execute", arguments={"query": "select 1"},
                                          execution_id="exec-a", target_identity="db", max_age_seconds=None)
    assert prior is not None
    assert prior.result_data is None
    assert not prior.result_data_available


def test_tool_ledger_marks_explicit_null_result_as_cached():
    ledger = ToolLedger()
    ledger.register_call(operation="collection.sql.execute", call_id="c1", arguments={},
                         iteration=1, agent_slug="a", phase_id="task-a")
    ledger.register_result(call_id="c1", success=True, data=None)
    assert ledger.entries[0].result_data_available
