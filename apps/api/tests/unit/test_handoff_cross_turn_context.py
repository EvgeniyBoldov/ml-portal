from __future__ import annotations

from uuid import UUID

import pytest

from app.runtime.context_outcome import RuntimeOutcomeProjector
from app.runtime.datastore_context import load_prior_result_inventory
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.orchestrator_contracts import PlannerContext, PlanRequest
from app.runtime.prompt_projections import preflight_context
from app.runtime.run_context import RunContext
from app.runtime.turn_state import RuntimeTurnState
from app.services.chat_context_contracts import TaskResultPayload
from app.services.chat_context_reducer import ChatContextReducer


RUN_ID = "00000000-0000-0000-0000-000000000111"
CHAT_ID = "00000000-0000-0000-0000-000000000222"
USER_ID = "00000000-0000-0000-0000-000000000333"
TENANT_ID = "00000000-0000-0000-0000-000000000444"
RESULT_ID = "result-snapshot-1"


def test_verified_task_receipt_survives_outcome_and_chat_context_contract() -> None:
    state = RuntimeTurnState.from_seed(
        run_id=UUID(RUN_ID), chat_id=UUID(CHAT_ID), user_id=UUID(USER_ID),
        tenant_id=UUID(TENANT_ID), goal="inspect data", current_user_query="inspect it",
        memory_bundle={},
    )
    state.task_results = [{
        "plan_id": "plan-1", "task_entity_id": "task-1", "outcome": "completed",
        "description": "Inspected a prior dataset.",
        "verified": {"receipts": [{
            "success": True, "result_id": RESULT_ID, "operation": "result.read",
            "source_complete": False,
            "result_observation": {"result_id": RESULT_ID, "revision": 2, "offset": 10,
                                   "limit": 5, "read_complete": False, "next_offset": 15},
        }]},
    }]
    projection = RuntimeOutcomeProjector.project(
        runtime_state=state, chat_id=CHAT_ID, chat_turn_id="turn-1", terminal_state="completed",
    )
    operation = next(op for op in ChatContextReducer().reduce(projection=projection, expected_revision=0)
                     if op.kind == "task_result_ref")
    context_payload = TaskResultPayload.model_validate(operation.payload)

    assert context_payload.result_refs[0].result_id == RESULT_ID
    assert context_payload.result_refs[0].source_run_id == RUN_ID
    assert context_payload.result_refs[0].observation.next_offset == 15
    assert "payload" not in operation.payload


@pytest.mark.asyncio
async def test_prior_inventory_reauthorizes_and_exposes_history_import_without_payload(monkeypatch) -> None:
    from app.services import runtime_result_reuse_service

    class FakeReuseService:
        def __init__(self, _session):
            pass

        async def authorize_source_runs(self, **kwargs):
            assert kwargs == {"run_ids": [RUN_ID], "chat_id": CHAT_ID, "owner_id": USER_ID,
                              "branch_id": "branch-1"}
            return [RUN_ID]

        async def list_prior_snapshots(self, **kwargs):
            assert kwargs["tenant_id"] == TENANT_ID
            assert kwargs["user_id"] == USER_ID
            assert kwargs["limit"] <= 30
            assert kwargs["selected_result_ids"] == [RESULT_ID]
            return {"status": "ready", "source_run_id": RUN_ID, "offset": 0, "limit": 30,
                    "total": 1, "next_offset": None, "catalog_complete": True,
                    "items": [{"result_id": RESULT_ID, "source_run_id": RUN_ID,
                               "operation": "result.read", "revision": 2, "row_count": 100,
                               "source_total": 300, "source_complete": False,
                               "payload_type": "json", "importable": True,
                               "snapshot_only": True, "payload": {"secret": "never forward"}}]}

    monkeypatch.setattr(runtime_result_reuse_service, "RuntimeResultReuseService", FakeReuseService)
    snapshot = {"task_result_refs": [{"source_run_id": RUN_ID, "result_refs": [{"result_id": RESULT_ID}]}]}
    inventory = await load_prior_result_inventory(
        session=object(), chat_snapshot=snapshot, chat_id=CHAT_ID, owner_id=USER_ID,
        branch_id="branch-1", tenant_id=TENANT_ID, user_id=USER_ID,
    )

    assert inventory["coverage"] == "complete"
    result = inventory["items"][0]
    assert result["source_run_id"] == RUN_ID
    assert result["snapshot_only"] is True
    assert result["fresh_retrieval"] is False
    assert result["import"]["tool"] == "result.import"
    assert result["import"]["arguments"] == {
        "source_run_id": RUN_ID, "result_id": RESULT_ID, "revision": 2,
    }
    assert "payload" not in result
    assert inventory["source_runs"][0]["history"]["tool"] == "result.history"

    run_context = RunContext(prior_result_inventory=inventory)
    plan_request = PlanRequest(context=PlannerContext(
        goal="sort prior results", trigger="followup", execution_ledger={},
        prior_result_inventory=run_context.prior_result_inventory,
    ))
    planner_input = PlannerInputBuilder().build_graph_request(plan_request)
    assert planner_input["prior_result_inventory"]["items"][0]["result_id"] == RESULT_ID
    assert planner_input["prior_result_inventory"]["items"][0]["import"]["arguments"]["revision"] == 2
    _, preflight_chat = preflight_context({}, {"prior_result_inventory": inventory},
                                         user_request="sort prior results")
    assert preflight_chat["prior_result_inventory"]["items"][0]["result_id"] == RESULT_ID


@pytest.mark.asyncio
async def test_unauthorized_source_run_is_explicitly_partial_not_empty_success(monkeypatch) -> None:
    from app.services import runtime_result_reuse_service

    class FakeReuseService:
        def __init__(self, _session):
            pass

        async def authorize_source_runs(self, **kwargs):
            return []

    monkeypatch.setattr(runtime_result_reuse_service, "RuntimeResultReuseService", FakeReuseService)
    inventory = await load_prior_result_inventory(
        session=object(), chat_snapshot={"task_result_refs": [{"source_run_id": RUN_ID}]},
        chat_id=CHAT_ID, owner_id=USER_ID, branch_id="branch-1", tenant_id=TENANT_ID, user_id=USER_ID,
    )

    assert inventory["items"] == []
    assert inventory["coverage"] == "partial"
    assert inventory["omitted_source_runs"] == 1
    assert inventory["status"] == "unavailable"
