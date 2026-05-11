import pytest

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_contracts import (
    build_response_contract,
    validate_role_contracts,
    get_role_output_model,
)


def test_planner_contract_has_json_format_and_kind_enum() -> None:
    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    assert contract["format"] == "json"
    schema = contract["schema"]
    assert "kind" in schema["properties"]
    # Use set comparison - order doesn't matter for enum values
    assert set(schema["properties"]["kind"]["enum"]) == {
        "direct_answer",
        "clarify",
        "call_agent",
        "ask_user",
        "final",
        "abort",
    }
    assert "kind" in schema["required"]
    assert "rationale" in schema["required"]
    variants = schema["oneOf"]
    assert isinstance(variants, list)
    assert any(v.get("title") == "call_agent" for v in variants)
    assert any(v.get("title") == "clarify" for v in variants)


def test_planner_contract_is_aligned_with_runtime_model() -> None:
    from app.runtime.planner.planner import PlannerLLMOutput

    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    schema = contract["schema"]
    runtime_schema = PlannerLLMOutput.model_json_schema()

    contract_keys = set(schema["properties"].keys())
    runtime_keys = set(runtime_schema["properties"].keys())
    assert contract_keys == runtime_keys

    contract_kind_enum = set(schema["properties"]["kind"]["enum"])
    runtime_kind_enum = set(runtime_schema["properties"]["kind"]["enum"])
    assert contract_kind_enum == runtime_kind_enum


def test_planner_contract_has_conditional_markers() -> None:
    """Contract should include x_when markers for conditional fields."""
    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    schema = contract["schema"]
    props = schema["properties"]

    assert props["agent_slug"].get("x_when") == "kind=call_agent"
    assert props["agent_input"].get("x_when") == "kind=call_agent"
    assert props["question"].get("x_when") == "kind=clarify"
    assert props["final_answer"].get("x_when") == "kind=direct_answer|final"


def test_fact_extractor_contract_is_json_from_pydantic() -> None:
    """Fact extractor contract is JSON schema generated from _LLMFactOutput Pydantic model."""
    contract = build_response_contract(SystemLLMRoleType.FACT_EXTRACTOR)
    assert contract["format"] == "json"
    schema = contract["schema"]
    # Schema should have facts property (exact structure depends on Pydantic $ref handling)
    assert "facts" in schema.get("properties", {}), "facts property should exist in schema"


def test_synthesizer_contract_plain_text() -> None:
    contract = build_response_contract(SystemLLMRoleType.SYNTHESIZER)
    assert contract["format"] == "plain_text"
    assert contract["schema"] is None
    assert isinstance(contract["plain_text"]["criteria"], list)
    assert contract["failure_policy"]["on_invalid"] == "accept_with_runtime_safety_filters"


# =============================================================================
# Contract validation and format_locked tests
# =============================================================================


def test_all_json_roles_have_format_locked_true() -> None:
    """All JSON contracts must have format_locked=True (built-in roles are fixed)."""
    json_roles = [
        SystemLLMRoleType.PLANNER,
        SystemLLMRoleType.TRIAGE,
        SystemLLMRoleType.FACT_EXTRACTOR,
        SystemLLMRoleType.SUMMARY_COMPACTOR,
    ]
    for role in json_roles:
        contract = build_response_contract(role)
        assert contract["format"] == "json"
        assert contract.get("format_locked") is True, f"{role.value} should have format_locked=True"


def test_all_plain_text_roles_have_format_locked_true() -> None:
    """Plain text contracts also have format_locked=True."""
    plain_roles = [
        SystemLLMRoleType.SYNTHESIZER,
        SystemLLMRoleType.SUMMARY,
        SystemLLMRoleType.MEMORY,
    ]
    for role in plain_roles:
        contract = build_response_contract(role)
        assert contract["format"] == "plain_text"
        assert contract.get("format_locked") is True, f"{role.value} should have format_locked=True"


def test_validate_role_contracts_passes_for_valid_roles() -> None:
    """Startup validation should pass for all correctly configured roles."""
    errors = validate_role_contracts()
    assert errors == {}, f"Unexpected validation errors: {errors}"


def test_get_role_output_model_returns_correct_models() -> None:
    """Registry should return correct Pydantic models for JSON roles."""
    from app.runtime.planner.planner import PlannerLLMOutput
    from app.runtime.memory.fact_extractor import _LLMFactOutput
    from app.runtime.memory.summary_compactor import _LLMSummaryOutput

    assert get_role_output_model(SystemLLMRoleType.PLANNER) is PlannerLLMOutput
    assert get_role_output_model(SystemLLMRoleType.FACT_EXTRACTOR) is _LLMFactOutput
    assert get_role_output_model(SystemLLMRoleType.SUMMARY_COMPACTOR) is _LLMSummaryOutput
    # Triage has no model yet (manual contract)
    assert get_role_output_model(SystemLLMRoleType.TRIAGE) is None


# =============================================================================
# Snapshot-style schema completeness tests
# =============================================================================


def test_planner_contract_has_all_required_fields() -> None:
    """Ensure planner contract includes all expected fields from Pydantic model."""
    from app.runtime.planner.planner import PlannerLLMOutput

    contract = build_response_contract(SystemLLMRoleType.PLANNER)
    schema = contract["schema"]

    expected_fields = set(PlannerLLMOutput.model_fields.keys())
    actual_fields = set(schema["properties"].keys())

    assert actual_fields == expected_fields, f"Missing fields: {expected_fields - actual_fields}"


def test_summary_compactor_contract_has_all_required_fields() -> None:
    """Ensure summary compactor contract matches Pydantic model."""
    from app.runtime.memory.summary_compactor import _LLMSummaryOutput

    contract = build_response_contract(SystemLLMRoleType.SUMMARY_COMPACTOR)
    schema = contract["schema"]

    expected_fields = set(_LLMSummaryOutput.model_fields.keys())
    actual_fields = set(schema["properties"].keys())

    assert actual_fields == expected_fields, f"Missing fields: {expected_fields - actual_fields}"


def test_fact_extractor_contract_has_all_required_fields() -> None:
    """Ensure fact extractor contract matches Pydantic model."""
    from app.runtime.memory.fact_extractor import _LLMFactOutput

    contract = build_response_contract(SystemLLMRoleType.FACT_EXTRACTOR)
    schema = contract["schema"]

    expected_fields = set(_LLMFactOutput.model_fields.keys())
    actual_fields = set(schema["properties"].keys())

    assert actual_fields == expected_fields, f"Missing fields: {expected_fields - actual_fields}"


# =============================================================================
# Triage contract (manual schema until Pydantic model is created)
# =============================================================================


def test_triage_contract_is_json_with_expected_fields() -> None:
    """Triage uses manual contract with all expected triage fields."""
    contract = build_response_contract(SystemLLMRoleType.TRIAGE)
    assert contract["format"] == "json"
    schema = contract["schema"]

    assert "type" in schema["properties"]
    assert "confidence" in schema["properties"]
    assert "reason" in schema["properties"]
    assert "answer" in schema["properties"]
    assert "clarify_prompt" in schema["properties"]
    assert "goal" in schema["properties"]
    assert "agent_hint" in schema["properties"]
    assert "resume_run_id" in schema["properties"]

    assert schema["properties"]["type"]["enum"] == ["final", "clarify", "orchestrate", "resume"]
    assert "type" in schema["required"]
    assert "confidence" in schema["required"]
    assert "reason" in schema["required"]
