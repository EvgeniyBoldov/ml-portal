"""The provider must see the same planner envelope rules as local validation."""
from __future__ import annotations

import pytest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import IterationProposal
from app.runtime.planner.graph_planner import PlannerStep
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import InMemoryPlanStore, PlanValidationError
from app.runtime.planner.prompt_contract import PLANNER_RUNTIME_CONTRACT
from app.models.system_llm_role import SystemLLMRoleType
from app.services.runtime_limits_service import ModelCallLimits


BRIEF = {
    "user_question": "Inspect a server",
    "planned_work": "Retrieve the server from the requested source",
    "purpose": "Answer the server question",
    "answer_requirements": "Use retrieved information only",
}
TASK = {
    "task_id": "fetch_server_1",
    "executor": "inventory",
    "intent": "Retrieve server information",
    "instructions": "Read the server from the requested inventory source.",
}


@pytest.mark.parametrize("proposal", [
    {"terminal": "planner"},
    {"terminal": "planner", "tasks": []},
    {"terminal": "planner", "tasks": [], "resolutions": [{
        "task_id": "init_001", "action": "exclude_from_scope",
        "reason": "Initial task placeholder resolution to clear ledger state.",
    }]},
    {"terminal": "planner", "tasks": [TASK], "synthesis_brief": BRIEF},
    {"terminal": "synthesis"},
    {"terminal": "synthesis", "synthesis_brief": None},
])
def test_nested_provider_schema_rejects_invalid_iteration(proposal):
    response = {"kind": "proposal", "proposal": proposal}
    with pytest.raises(ValidationError):
        PlannerStep.model_validate(response)
    schema = StructuredLLMCall._compact_response_schema(PlannerStep.model_json_schema())
    assert not Draft202012Validator(schema).is_valid(response)


@pytest.mark.parametrize("proposal", [
    {"terminal": "planner", "tasks": [TASK]},
    {"terminal": "synthesis", "tasks": [TASK], "synthesis_brief": BRIEF},
    {"terminal": "synthesis", "tasks": [], "synthesis_brief": BRIEF},
])
def test_direct_and_nested_schema_accept_valid_handoffs(proposal):
    IterationProposal.model_validate(proposal)
    Draft202012Validator(IterationProposal.model_json_schema()).validate(proposal)
    response = {"kind": "proposal", "proposal": proposal}
    PlannerStep.model_validate(response)
    Draft202012Validator(PlannerStep.model_json_schema()).validate(response)


@pytest.mark.parametrize("response", [
    {"kind": "proposal"},
    {"kind": "tool_call"},
    {"kind": "interaction"},
    {"kind": "proposal", "proposal": {"terminal": "planner", "tasks": [TASK]},
     "tool_call": {"tool": "memory.search", "arguments": {"query": "server"}}},
])
def test_provider_schema_requires_only_the_selected_payload(response):
    with pytest.raises(ValidationError):
        PlannerStep.model_validate(response)
    assert not Draft202012Validator(PlannerStep.model_json_schema()).is_valid(response)


@pytest.mark.parametrize("terminal", ["planner", "synthesis"])
def test_tasks_are_scheduled_before_either_terminal(terminal):
    proposal = IterationProposal.model_validate({
        "terminal": terminal, "tasks": [TASK],
        "synthesis_brief": BRIEF if terminal == "synthesis" else None,
    })
    compiled = GraphOrchestrator._compile(
        proposal, [{"slug": TASK["executor"], "supports_dynamic_contracts": True}],
        {"tasks": [], "needs": []},
    )
    store = InMemoryPlanStore()
    plan = store.create(goal=BRIEF["user_question"], root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], compiled)
    decision = store.next_decision(plan["id"])
    assert decision.kind.value == "execute_task"
    assert decision.task_id == TASK["task_id"]


def test_initial_ledger_cannot_be_cleared_with_a_fictitious_resolution():
    proposal = IterationProposal.model_validate({
        "terminal": "planner", "tasks": [TASK],
        "resolutions": [{"task_id": "init_001", "action": "exclude_from_scope", "reason": "clear ledger"}],
    })
    with pytest.raises(PlanValidationError, match="prior incomplete task"):
        GraphOrchestrator._compile(proposal, [{"slug": TASK["executor"]}], {"tasks": [], "needs": []})


def test_runtime_delegation_example_matches_the_envelope_and_input_catalog():
    from app.services.orchestration_prompts import PLANNER_PROMPT_V3
    # Operator-managed role examples are the sole source of demonstrations.
    assert "Output: " not in PLANNER_RUNTIME_CONTRACT
    example_input = PLANNER_PROMPT_V3["examples"][0]["input"]
    output = PLANNER_PROMPT_V3["examples"][0]["output"]
    Draft202012Validator(PlannerStep.model_json_schema()).validate(output)
    step = PlannerStep.model_validate(output)
    compiled = GraphOrchestrator._compile(step.proposal, example_input["available_agents"], example_input["execution_ledger"])
    assert compiled.tasks
    assert compiled.resolutions == []


@pytest.mark.asyncio
async def test_production_empty_planner_response_can_be_corrected_to_a_schedulable_task(monkeypatch):
    import json

    invalid = {"kind": "proposal", "proposal": {
        "terminal": "planner", "synthesis_brief": None, "bindings": [],
        "resolutions": [{"task_id": "init_001", "action": "exclude_from_scope", "reason": "clear ledger"}],
    }}
    corrected = {"kind": "proposal", "proposal": {
        "terminal": "planner", "tasks": [TASK], "bindings": [], "resolutions": [],
    }}
    requests = []

    async def chat(messages, **kwargs):
        requests.append(deepcopy({"messages": messages, **kwargs}))
        return json.dumps(invalid if len(requests) == 1 else corrected)

    call = StructuredLLMCall(session=AsyncMock(), llm_client=SimpleNamespace(chat=chat))
    call.role_service.get_role_config = AsyncMock(return_value={"role_type": "planner", "model": "configured-model"})
    call.limits_service.resolve_model = AsyncMock(return_value=ModelCallLimits(request_timeout_s=1, max_retries=1))
    monkeypatch.setattr("app.runtime.llm.structured.asyncio.sleep", AsyncMock())
    payload = {"goal": BRIEF["user_question"], "execution_ledger": {"tasks": [], "needs": []},
               "available_agents": [{"slug": TASK["executor"], "supports_dynamic_contracts": True}]}

    result = await call.invoke(role=SystemLLMRoleType.PLANNER, payload=payload, schema=PlannerStep)

    assert len(requests) == 2
    provider_schema = requests[0]["params"]["response_format"]["json_schema"]["schema"]
    assert not Draft202012Validator(provider_schema).is_valid(invalid)
    Draft202012Validator(provider_schema).validate(corrected)
    assert "planner terminal requires at least one task" in requests[1]["messages"][-1]["content"]
    compiled = GraphOrchestrator._compile(result.value.proposal, payload["available_agents"], payload["execution_ledger"])
    store = InMemoryPlanStore()
    plan = store.create(goal=payload["goal"], root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], compiled)
    assert store.next_decision(plan["id"]).kind.value == "execute_task"
