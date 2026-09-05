from __future__ import annotations

import pytest

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_contracts import (
    build_response_contract,
    get_role_output_model,
    validate_role_contracts,
)


def test_planner_contract_matches_runtime_model() -> None:
    from app.runtime.planner.graph_planner import PlannerGraphOutput

    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    assert contract["format"] == "json"
    assert set(contract["schema"]["properties"]) == set(PlannerGraphOutput.model_fields)
    assert set(contract["schema"]["properties"]["action"]["enum"]) == {
        "apply_graph", "ask_user", "fail",
    }


@pytest.mark.parametrize(
    "role",
    [
        SystemLLMRoleType.PLANNER,
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
