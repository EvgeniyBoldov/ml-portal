import json

import pytest

from app.runtime.orchestrator import GraphOrchestrator


def test_compacted_planner_ledger_keeps_every_task_and_respects_size_limit() -> None:
    tasks = [
        {
            "task_id": f"task-{index:03d}",
            "iteration_id": "iteration-1",
            "intent": "Check a source",
            "executor": "researcher",
            "instructions": "inspect " + ("detail " * 200),
            "status": "failed" if index == 44 else "completed",
            "attempts": 1,
            "result": {"reason_code": "source_unavailable", "outputs": {"large": "x" * 5_000}},
        }
        for index in range(45)
    ]
    ledger = {"plan_status": "active", "iterations": [], "tasks": tasks,
              "needs": [], "bindings": [], "resolutions": []}
    max_chars = 12_000

    compacted = GraphOrchestrator._compact_ledger(ledger, max_chars)

    assert len(json.dumps(compacted, ensure_ascii=False)) <= max_chars
    assert [task["task_id"] for task in compacted["tasks"]] == [task["task_id"] for task in tasks]
    assert compacted["tasks"][-1]["status"] == "failed"


def test_planner_ledger_compaction_fails_explicitly_when_structural_state_cannot_fit() -> None:
    ledger = {"tasks": [
        {"task_id": f"task-{index}-" + ("x" * 80), "status": "failed", "attempts": 1}
        for index in range(4)
    ]}

    with pytest.raises(ValueError, match="structural state exceeds max_chars"):
        GraphOrchestrator._compact_ledger(ledger, max_chars=100)
