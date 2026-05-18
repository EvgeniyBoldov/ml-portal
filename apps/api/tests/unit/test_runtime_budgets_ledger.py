from __future__ import annotations

import pytest

from app.runtime.budgets import BudgetExceededError, BudgetLimitsResolver, RunBudgetLedger


def _limits():
    return BudgetLimitsResolver.resolve_from_platform(
        planner_max_steps=3,
        planner_max_wall_time_ms=120_000,
        platform_config={
            "runtime_budget": {
                "max_planner_iterations": 3,
                "max_agent_steps": 4,
                "max_tool_calls_total": 2,
                "max_wall_time_ms": 120_000,
            }
        },
    ).run


def test_ledger_records_and_snapshots_metrics() -> None:
    ledger = RunBudgetLedger(limits=_limits())
    ledger.register_sub(owner_scope="agent", owner_id="agent-1")

    ledger.record_planner_iteration(owner_id="orch-1")
    ledger.record_agent_step(owner_id="agent-1")
    ledger.record_tool_call(owner_id="agent-1")
    ledger.record_retry(owner_id="agent-1")
    ledger.record_tokens(tokens_in=10, tokens_out=15, owner_id="agent-1")

    snap = ledger.snapshot()
    assert snap["consumed_planner_iterations"] == 1
    assert snap["consumed_agent_steps"] == 1
    assert snap["consumed_tool_calls"] == 1
    assert snap["consumed_retries"] == 1
    assert snap["tokens_in"] == 10
    assert snap["tokens_out"] == 15
    assert snap["tokens_total"] == 25


def test_ledger_consume_raises_on_exceed() -> None:
    ledger = RunBudgetLedger(limits=_limits())

    ledger.consume("tool_calls", 1, owner_scope="agent", owner_id="agent-1")
    ledger.consume("tool_calls", 1, owner_scope="agent", owner_id="agent-1")

    with pytest.raises(BudgetExceededError):
        ledger.consume("tool_calls", 1, owner_scope="agent", owner_id="agent-1")


def test_ledger_emits_budget_snapshot_payloads() -> None:
    emitted: list[dict] = []
    ledger = RunBudgetLedger(limits=_limits(), emit=emitted.append)

    ledger.record_agent_step(owner_id="agent-1")

    assert emitted
    payload = emitted[-1]
    assert payload["owner_scope"] == "agent"
    assert payload["owner_id"] == "agent-1"
    assert payload["reason"] == "agent_step"
    assert payload["delta"] == {"agent_steps": 1}
    assert "snapshot" in payload
    assert "agent_steps" in payload["snapshot"]
