from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.memory.effective_scope import memory_visible_for_scope, project_memory_context
from app.runtime.memory.search import MemorySearchService


def search_service():
    service = MemorySearchService(object())
    service._search_context = AsyncMock(return_value={"items": [], "projects": [], "facts": [],
        "glossary": [], "uncertainties": [], "search_scope": {}})
    return service


def test_execution_context_is_a_fact_with_common_rules_selector_even_without_projects():
    fact = memory_execution_context(["team.ops", "project.a", "project.b"], revision=4)
    assert fact["scope_keys"] == ["team.ops", "project.a", "project.b"]
    assert fact["revision"] == 4
    assert memory_execution_context([])["scope_keys"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("teams,projects,expected", [
    (None, None, [["team.ops", "project.a"], ["team.ops", "project.b"]]),
    (["ops"], ["b"], [["team.ops", "project.b"]]),
    (None, [], [["team.ops"]]),
    (None, ["all"], [["team.ops", "project.all"]]),
    (None, ["a", "all"], [["team.ops", "project.a"]]),
])
async def test_context_teams_are_retained_for_each_project_selection(teams, projects, expected):
    service = search_service()
    result = await service.search(query="rules", tenant_id=None, team_keys=teams, project_keys=projects,
        context_scope_keys=["team.ops", "project.a", "project.b"], enforce_context=True)
    assert result.get("success") is not False
    assert [call.kwargs["scope_keys"] for call in service._search_context.await_args_list] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("teams,projects,error", [
    ([], [], "context_teams_required"),
    (["other"], ["a"], "context_teams_required"),
    (None, ["other"], "project_not_in_execution_context"),
    (["ops", "other"], ["a"], "context_teams_required"),
])
async def test_caller_cannot_invent_projects_or_remove_context_teams(teams, projects, error):
    service = search_service()
    result = await service.search(query="rules", tenant_id=None, team_keys=teams, project_keys=projects,
        context_scope_keys=["team.ops", "project.a"], enforce_context=True)
    assert result["error_code"] == error
    service._search_context.assert_not_awaited()


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
