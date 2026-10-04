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
    assert fact["team_keys"] == ["team.ops"]
    assert fact["project_keys"] == ["project.a", "project.b", "project.all"]
    assert fact["focused_project_keys"] == ["project.a", "project.b"]
    assert fact["revision"] == 4
    assert memory_execution_context([])["project_keys"] == ["project.all"]


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


@pytest.mark.parametrize("bindings,expected", [
    (["team.ops", "project.all"], True), (["team.all", "project.all"], True),
    (["team.ops", "project.a"], False), (["team.other", "project.all"], False),
    (["team.ops"], False),
])
def test_common_project_query_excludes_concrete_and_non_project_atoms(bindings, expected):
    assert memory_visible_for_scope({"scope_keys": bindings}, ["team.ops", "project.all"]) == expected


def test_explicit_common_rules_result_survives_projection_without_enumerating_projects():
    common = {"id": "common", "scope_keys": ["team.ops", "project.all"],
              "query_scope_keys": ["team.ops", "project.all"]}
    result = project_memory_context({"items": [common], "groups": [{"project_keys": ["project.all"],
        "items": [common]}]}, ["team.ops"])
    assert result["items"] == [common] and result["groups"][0]["items"] == [common]
    assert not project_memory_context({"items": [common]}, ["team.other"])["items"]


@pytest.mark.asyncio
async def test_agent_tool_uses_chat_fact_even_when_task_focus_is_narrower(monkeypatch):
    from app.agents.builtins import memory_search as builtin
    session = AsyncMock()
    session.__aenter__.return_value = object()
    monkeypatch.setattr(builtin, "get_session_factory", lambda: lambda: session)
    service = search_service()
    monkeypatch.setattr(builtin, "MemorySearchService", lambda _: service)
    fact = memory_execution_context(["team.ops", "team.net", "project.a", "project.b"])
    ctx = SimpleNamespace(user_id=None, tenant_id=None, extra={"memory_execution_context": fact,
        "project_context": {"effective_scope_keys": ["team.ops", "project.a"]}})
    result = await builtin.MemorySearchTool().v1_0_0(ctx, {"query": "rules", "project_keys": ["b"]})
    assert result.success
    assert result.data["execution_context"] == fact
    assert service._search_context.await_args.kwargs["scope_keys"] == ["team.ops", "team.net", "project.b"]


def test_root_common_rules_request_does_not_replace_concrete_chat_focus():
    from app.runtime.turn_preflight import MemoryRequest, TurnPreflightDecision, _canonical_scope_selection
    decision = TurnPreflightDecision(route="recall", memory_request=MemoryRequest(
        query="rules", direction="common rules", project_keys=["project.all"]))
    assert _canonical_scope_selection(decision).keys == []
    assert decision.memory_request.project_keys == ["project.all"]
