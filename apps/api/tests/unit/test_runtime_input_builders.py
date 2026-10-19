from __future__ import annotations

import json
from uuid import uuid4

from app.runtime.input_builders import PlannerInputBuilder, SynthesizerInputBuilder
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext


def _request(**overrides):
    context = PlannerContext(**{
        "goal": "Проверить конфигурацию",
        "trigger": "task_outcome",
        "execution_ledger": {"tasks": [{"task_id": "inspect", "status": "completed"}]},
        "available_agents": [{"slug": "viewer", "description": "Просмотр данных"}],
        "available_artifacts": [],
        "memory_context": [],
        **overrides,
    })
    return PlanRequest(context=context, plan_id=uuid4(), run_id=uuid4())


def test_graph_planner_input_builder_uses_only_iteration_contract():
    payload = PlannerInputBuilder().build_graph_request(_request())

    assert set(payload) == {
        "goal", "trigger", "execution_ledger", "available_artifacts", "memory_context", "task_brief",
        "available_agents", "iteration_contract",
        "scope_context", "planner_search_results", "execution_context",
    }
    assert payload["trigger"] == "task_outcome"
    assert payload["execution_ledger"]["tasks"][0]["task_id"] == "inspect"
    assert payload["iteration_contract"]["terminal"] == ["planner", "synthesis"]
    assert payload["execution_context"]["scope_keys"] == []


def test_planner_receives_execution_context_as_an_application_fact():
    payload = PlannerInputBuilder().build_graph_request(_request(scope_context={
        "keys": ["company", "a"], "revision": 3}))
    assert payload["execution_context"]["scope_keys"] == ["company", "a"]
    assert payload["execution_context"]["revision"] == 3


def test_graph_planner_input_builder_exposes_fresh_retrieval_capability():
    payload = PlannerInputBuilder().build_graph_request(_request(available_agents=[{
        "slug": "live-system", "description": "Reads the live system",
        "requires_fresh_retrieval": True,
    }]))

    assert payload["available_agents"][0]["requires_fresh_retrieval"] is True


def test_graph_planner_input_builder_normalizes_artifact_contexts():
    payload = PlannerInputBuilder().build_graph_request(_request(available_artifacts=[{
        "ref": {"artifact_id": "artifact-1", "file_name": "notes.txt", "content_type": "text/plain"},
        "snippet": "hello", "snippet_status": "ready", "readable": True,
    }]))

    assert payload["available_artifacts"] == [{
        "artifact_id": "artifact-1", "is_current": False, "representation_id": None, "source_complete": False, "file_name": "notes.txt", "content_type": "text/plain",
        "size_bytes": None, "origin": {}, "description": None,
        "snippet": "hello", "snippet_status": "ready",
        "readable": True, "truncated": False,
    }]


def test_synthesizer_input_builder_serializes_only_the_prebuilt_context():
    context = {"synthesis_brief": {"purpose": "answer"}, "completed_task_reports": []}
    messages = SynthesizerInputBuilder().build(synthesis_context=context, system_prompt="sys")

    assert messages[0]["content"] == "sys"
    assert json.loads(messages[1]["content"]) == context


def test_memory_group_projection_preserves_empty_and_failed_groups_without_merging():
    from app.runtime.input_builders import compact_memory_tool_records
    records = [{"tool": "memory.search", "result": {"backend": "hipporag", "groups": [
        {"scope_slug": "company", "status": "completed", "success": True, "items": [{"text": "company-only", "subject": "rule"}]},
        {"scope_slug": "a", "status": "completed", "success": True, "items": []},
        {"scope_slug": "b", "status": "failed", "success": False, "items": [], "error_code": "memory_search_failed"},
    ]}}]
    projection = compact_memory_tool_records(records)[0]["result"]
    assert projection["group_count"] == 3
    assert [group["scope_slug"] for group in projection["groups"]] == ["company", "a", "b"]
    assert projection["groups"][1]["items"] == []
    assert not projection["groups"][2]["success"]
    assert "items" not in projection
