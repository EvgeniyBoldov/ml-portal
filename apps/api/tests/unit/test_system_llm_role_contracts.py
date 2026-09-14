from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_contracts import (
    build_response_contract,
    get_role_output_model,
    validate_role_contracts,
)


def test_planner_contract_matches_runtime_model() -> None:
    from app.runtime.planner.graph_planner import PlannerStep

    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    assert contract["format"] == "json"
    assert set(contract["schema"]["properties"]) == set(PlannerStep.model_fields)
    assert contract["schema"]["properties"]["kind"]
    PlannerStep.model_validate(contract["examples_v2"]["outputs"]["default"])


def test_planner_step_accepts_the_previous_bare_proposal_during_rollout() -> None:
    from app.runtime.planner.graph_planner import PlannerStep

    step = PlannerStep.model_validate({
        "tasks": [], "terminal": "planner", "bindings": [], "resolutions": [],
    })
    assert step.kind == "proposal"
    assert step.proposal is not None


def test_preflight_rejects_chat_project_memory_candidate() -> None:
    from app.runtime.turn_preflight import MemoryCandidate

    with pytest.raises(ValidationError):
        MemoryCandidate.model_validate({
            "scope": "project", "subject": "network.rule", "value": "use approval",
        })


def test_direct_synthesis_requires_runtime_owned_answer_material() -> None:
    from app.runtime.turn_preflight import TurnPreflightDecision

    decision = TurnPreflightDecision.model_validate({
        "route": "synthesis",
        "synthesis_brief": {
            "synthesis_brief": {
                "user_question": "Что такое SRK?", "planned_work": "Ответить",
                "purpose": "Объяснение", "answer_requirements": "Коротко",
            },
            "answer_draft": "SRK — термин из предоставленного контекста.",
        },
    })
    assert decision.synthesis_brief is not None


@pytest.mark.parametrize(
    "role",
    [
        SystemLLMRoleType.PLANNER,
        SystemLLMRoleType.TURN_PREFLIGHT,
        SystemLLMRoleType.MEMORY,
        SystemLLMRoleType.FACT_EXTRACTOR,
        SystemLLMRoleType.FACT_COMPACTOR,
    ],
)
def test_structured_runtime_roles_have_locked_json_contracts(role: SystemLLMRoleType) -> None:
    contract = build_response_contract(role)
    assert contract["format"] == "json"
    assert contract["format_locked"] is True
    assert get_role_output_model(role) is not None


def test_synthesizer_contract_is_plain_text() -> None:
    contract = build_response_contract(SystemLLMRoleType.SYNTHESIZER)
    assert contract["format"] == "plain_text"
    assert contract["format_locked"] is True


def test_runtime_role_contract_registry_is_valid() -> None:
    assert validate_role_contracts() == {}
