from __future__ import annotations

import pytest

from app.runtime.memory.content_contracts import content_contract_error, normalize_memory_content


def _procedure() -> dict:
    return {
        "goal": "Change VLAN",
        "applicability_conditions": ["Production"],
        "required_approvals": [],
        "prechecks": ["Create backup"],
        "steps": [{"instruction": "Apply VLAN", "expected_result": "VLAN applied", "confirmation_required": True}],
        "verification": ["Check connectivity"],
        "rollback": {"mode": "steps", "steps": ["Restore backup"], "reason": None},
        "exceptions": [],
    }


def test_procedure_contract_assigns_order_and_keeps_full_rollback() -> None:
    content = normalize_memory_content("procedure", _procedure())

    assert content["steps"] == [{
        "order": 1, "instruction": "Apply VLAN", "expected_result": "VLAN applied", "confirmation_required": True,
    }]
    assert content["rollback"]["steps"] == ["Restore backup"]


def test_persisted_procedure_remains_valid_for_review_and_publication() -> None:
    content = normalize_memory_content("procedure", _procedure())
    assert normalize_memory_content("procedure", content) == content
    assert content_contract_error("procedure", content) is None


def test_review_error_names_all_missing_and_misplaced_fields() -> None:
    error = content_contract_error("rule", {"definition": "Approval is required"})
    assert error is not None
    assert all(field in error for field in ("statement", "effect", "definition"))
    assert "обязательное поле отсутствует" in error


@pytest.mark.parametrize("content", [
    {"steps": []},
    {**_procedure(), "rollback": {"mode": "not_applicable", "steps": [], "reason": None}},
    {**_procedure(), "unknown": "must fail"},
])
def test_incomplete_or_unknown_procedure_content_is_rejected(content: dict) -> None:
    with pytest.raises(ValueError):
        normalize_memory_content("procedure", content)


def test_rule_and_constraint_contracts_normalize_lists() -> None:
    rule = normalize_memory_content("rule", {
        "statement": "Approval is required", "effect": "require",
        "conditions": ["Production", "production"], "required_approvals": [],
        "required_checks": [], "exceptions": [], "consequences": [],
    })
    constraint = normalize_memory_content("constraint", {
        "statement": "No direct access", "conditions": [], "limits": ["Bastion only"],
        "exceptions": [], "consequences": [],
    })

    assert rule["conditions"] == ["Production"]
    assert constraint["limits"] == ["Bastion only"]


def test_term_description_and_relationship_require_typed_content() -> None:
    assert normalize_memory_content("term", {"definition": "Configuration service"}) == {
        "definition": "Configuration service",
    }
    assert normalize_memory_content("description", {"summary": "Network automation", "details": []}) == {
        "summary": "Network automation", "details": [],
    }
    with pytest.raises(ValueError):
        normalize_memory_content("relationship", {"text": "uses service"})
