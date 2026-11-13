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


def test_graph_planner_input_builder_uses_the_current_ledger_payload():
    payload = PlannerInputBuilder().build_graph_request(_request())

    assert set(payload) == {
        "goal", "trigger", "execution_ledger", "resolution_targets", "datastore", "memory_context", "task_brief",
        "available_agents", "scope_context", "prior_result_inventory",
    }
    assert payload["trigger"] == "task_outcome"
    assert payload["execution_ledger"]["tasks"][0]["task_id"] == "inspect"
    assert payload["scope_context"] == {}
    assert payload["prior_result_inventory"] == {}


def test_graph_planner_input_builder_preserves_content_free_prior_result_inventory():
    prior = {"source_run_id": "prior-run", "items": [{"result_id": "prior-result",
        "revision": 3, "row_count": 2, "importable": True}], "catalog_complete": True}
    payload = PlannerInputBuilder().build_graph_request(_request(prior_result_inventory=prior))

    assert payload["prior_result_inventory"] == prior
    assert "payload" not in json.dumps(payload["prior_result_inventory"])


def test_planner_receives_current_scope_context():
    payload = PlannerInputBuilder().build_graph_request(_request(scope_context={
        "keys": ["company", "a"], "revision": 3}))
    assert payload["scope_context"] == {"keys": ["company", "a"], "revision": 3}


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

    entry = payload["datastore"]["items"][0]
    assert entry["artifact_id"] == "artifact-1"
    assert entry["file_name"] == "notes.txt"
    assert entry["representation_status"] == "ready"
    assert "snippet" not in entry
    assert "hello" not in json.dumps(payload["datastore"])



def test_synthesizer_input_builder_serializes_only_the_prebuilt_context():
    context = {"synthesis_brief": {"purpose": "answer"}, "completed_task_reports": []}
    messages = SynthesizerInputBuilder().build(synthesis_context=context, system_prompt="sys")

    assert messages[0]["content"] == "sys"
    assert json.loads(messages[1]["content"]) == context


def test_planner_inventory_includes_task_files_and_results_but_filters_deleted_files():
    payload = PlannerInputBuilder().build_graph_request(_request(
        execution_ledger={"tasks": [{"result": {
            "attachments": [{"artifact_id": "generated", "file_name": "answer.md"}],
            "sources": [{"artifact_id": "removed", "file_name": "removed.pdf"}],
        }}]}, deleted_artifact_ids=["removed"],
        available_results=[{"result_id": "dataset", "task_id": "fetch", "operation": "api.list",
                            "row_count": 0, "observed_schema": {}, "source_complete": True}],
    ))
    assert [(item["kind"], item.get("artifact_id") or item.get("result_id"))
            for item in payload["datastore"]["items"]] == [("file", "generated"), ("result", "dataset")]


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


def test_grouped_memory_projection_is_bounded_and_reports_omitted_passages_without_mutating_evidence():
    from app.runtime.evidence_projection import bounded_grouped_memory
    from app.runtime.input_builders import compact_memory_search_result
    groups = [{"scope_slug": "a", "success": True, "items": [
        {"text": f"passage-{index}-" + ("x" * 8_000)} for index in range(4)
    ]}, {"scope_slug": "b", "success": False, "items": []}]
    source = {"groups": groups, "partial": True}
    projected = bounded_grouped_memory(source, token_budget=3_000)
    assert projected["evidence_coverage"] == "partial"
    assert projected["omitted_passage_ids"]
    assert projected["groups"][0]["items"]
    assert source["groups"] == groups
    tiny = bounded_grouped_memory(source, token_budget=1)
    assert tiny["evidence_coverage"] == "unavailable"
    assert source["groups"] == groups


def test_shared_projection_bounds_multiple_searches_and_large_read_receipt_together():
    from app.runtime.evidence_projection import bound_prompt_memory
    payload = {
        "memory_tool_results": [
            {"tool": "memory.search", "arguments": {"query": "first"}, "result": {"groups": [
                {"scope_slug": "company", "success": True, "items": [{"text": "A" * 2_000}]},
                {"scope_slug": "project", "success": False, "items": []},
            ]}},
            {"tool": "memory.search", "arguments": {"query": "second"}, "result": {"groups": [
                {"scope_slug": "company", "success": True, "items": [{"text": "B" * 2_000}]},
            ]}},
            {"tool": "file.data.read", "arguments": {"representation_id": "rep", "offset": 0},
             "result": {"success": True, "representation_id": "rep", "content": "C" * 20_000,
                        "next_offset": 50, "has_more": True}},
        ],
        "run_context": {"evidence": [{"id": "file-evidence", "tool": "file.data.read",
            "arguments": {"representation_id": "rep", "offset": 50}, "data": {"text": "D" * 20_000}}],
            "conversation_materials": [], "evidence_catalog": [{"id": "file-evidence", "tool": "file.data.read"}]},
        "execution_ledger": {"tasks": []},
    }
    bounded = bound_prompt_memory(payload, token_budget=1_000, model="gpt-4o-mini")
    records = bounded["memory_tool_results"]
    assert records[2]["arguments"] == {"representation_id": "rep", "offset": 0}
    assert "content" not in records[2]["result"]
    assert records[2]["result"]["next_offset"] == 50
    assert bounded["evidence_coverage"] in {"partial", "unavailable"}
    if "omitted_material_refs" in bounded["run_context"]:
        assert bounded["run_context"]["omitted_material_recovery"][0]["arguments"] == {
            "representation_id": "rep", "offset": 50}
    assert payload["memory_tool_results"][2]["result"]["content"] == "C" * 20_000


async def test_payload_allowance_uses_model_window_prompt_and_response_schema(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.runtime.evidence_projection import prompt_payload_budget
    from app.services.runtime_limits_service import RuntimeLimitsService
    monkeypatch.setattr(RuntimeLimitsService, "resolve_model", AsyncMock(
        return_value=SimpleNamespace(context_window_tokens=10_000)))
    session = AsyncSession()

    class SmallSchema:
        @staticmethod
        def model_json_schema():
            return {"type": "object"}

    class LargeSchema:
        @staticmethod
        def model_json_schema():
            return {"description": "schema detail " * 400, "type": "object"}

    small = await prompt_payload_budget(session=session, model="chat-model", system_prompt="role rules", schema=SmallSchema)
    large = await prompt_payload_budget(session=session, model="chat-model", system_prompt="role rules", schema=LargeSchema)
    assert small is not None and 0 < small < 10_000
    assert large < small


def test_resolution_targets_preserve_all_completed_and_incomplete_task_ids():
    request = _request(execution_ledger={"tasks": [
        {"task_id": "done", "status": "completed"},
        {"task_id": "failed", "status": "failed"},
        {"task_id": "need", "status": "needs_dependency"},
    ]})
    payload = PlannerInputBuilder().build_graph_request(request)
    assert payload["resolution_targets"] == {
        "completed_task_ids": ["done"], "incomplete_task_ids": ["failed", "need"],
    }
