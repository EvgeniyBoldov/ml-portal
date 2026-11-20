import pytest

from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.memory.effective_scope import memory_visible_for_scope, project_memory_context


def test_execution_context_is_a_fact_with_common_rules_selector_even_without_projects():
    fact = memory_execution_context(["team.ops", "project.a", "project.b"], revision=4)
    assert fact["scope_keys"] == ["team.ops", "project.a", "project.b"]
    assert fact["revision"] == 4
    assert memory_execution_context([])["scope_keys"] == []


@pytest.mark.parametrize("bindings,selected,expected", [
    (["company", "dcbox"], ["company"], True),
    (["company"], ["dcbox"], False),
    (["company"], ["company"], True),
    (["nims"], ["company", "dcbox"], False),
    (["company"], [], False),
])
def test_memory_visibility_uses_exact_flat_scope_slugs(bindings, selected, expected):
    assert memory_visible_for_scope({"scope_keys": bindings}, selected) == expected


def test_explicit_common_rules_result_survives_projection_without_enumerating_projects():
    common = {"id": "common", "scope_keys": ["team.ops", "project.all"],
              "query_scope_keys": ["team.ops", "project.all"]}
    result = project_memory_context({"items": [common], "groups": [{"project_keys": ["project.all"],
        "items": [common]}]}, ["team.ops"])
    assert result["items"] == [common] and result["groups"][0]["items"] == [common]
    assert not project_memory_context({"items": [common]}, ["team.other"])["items"]


def test_root_document_search_does_not_replace_concrete_chat_focus():
    from app.runtime.turn_preflight import TurnPreflightDecision, _canonical_scope_selection
    decision = TurnPreflightDecision(route="tool_call", tool_call={
        "tool": "memory.search", "arguments": {"query": "common rules"}})
    assert _canonical_scope_selection(decision).keys == []
    assert decision.tool_call.arguments.query == "common rules"
