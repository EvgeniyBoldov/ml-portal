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
        "goal", "trigger", "execution_ledger", "available_artifacts", "memory_context",
        "available_agents", "iteration_contract",
    }
    assert payload["trigger"] == "task_outcome"
    assert payload["execution_ledger"]["tasks"][0]["task_id"] == "inspect"
    assert payload["iteration_contract"]["terminal"] == ["planner", "synthesis"]


def test_graph_planner_input_builder_normalizes_artifact_contexts():
    payload = PlannerInputBuilder().build_graph_request(_request(available_artifacts=[{
        "ref": {"artifact_id": "artifact-1", "file_name": "notes.txt", "content_type": "text/plain"},
        "snippet": "hello", "snippet_status": "ready", "readable": True,
    }]))

    assert payload["available_artifacts"] == [{
        "artifact_id": "artifact-1", "file_name": "notes.txt", "content_type": "text/plain",
        "size_bytes": None, "snippet": "hello", "snippet_status": "ready",
        "readable": True, "truncated": False,
    }]


def test_synthesizer_input_builder_serializes_only_the_prebuilt_context():
    context = {"synthesis_brief": {"purpose": "answer"}, "completed_task_reports": []}
    messages = SynthesizerInputBuilder().build(synthesis_context=context, system_prompt="sys")

    assert messages[0]["content"] == "sys"
    assert json.loads(messages[1]["content"]) == context
