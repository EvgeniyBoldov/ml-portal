"""History belongs to preflight; downstream roles receive selected task material."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.orchestrator_contracts import PlanRequest, PlannerContext, TaskRequest
from app.runtime.run_context import RunContext


def test_run_projection_keeps_history_in_storage_only():
    context = RunContext(
        original_request="Check it again", goal="Check server alpha",
        chat_snapshot={"recent_anchor": {"assistant_outcome": "OLD_ANSWER"},
                       "task_result_refs": [{"safe_summary": "OLD_AGENT_REPORT"}]},
        recent_dialogue=[{"message_id": "old", "role": "assistant", "content": "OLD_DIALOGUE"}],
        synthesis_message="PREVIOUS_SYNTHESIS", generated_artifacts=[{"artifact_id": "old-file"}],
    )
    context.add_evidence("chat.history.read", {}, {"messages": context.recent_dialogue})
    context.add_evidence("file.read", {}, {"content": "UNSELECTED_FILE"})

    serialized = json.dumps(context.projection())
    for marker in ("OLD_ANSWER", "OLD_AGENT_REPORT", "OLD_DIALOGUE", "PREVIOUS_SYNTHESIS", "UNSELECTED_FILE"):
        assert marker not in serialized
    assert "OLD_ANSWER" in context.model_dump_json()
    assert context.projection()["original_request"] == "Check it again"


def test_preflight_selects_messages_and_sources_without_promoting_dialogue_to_evidence():
    context = RunContext(recent_dialogue=[
        {"message_id": "chosen", "role": "assistant", "content": "Rewrite this text", "truncated": True},
        {"message_id": "other", "role": "assistant", "content": "UNRELATED_ANSWER"},
    ])
    selected = context.add_evidence("file.read", {"artifact_id": "file"}, {"content": "SELECTED_SOURCE"})
    history = context.add_evidence("chat.history.read", {}, {"messages": [
        {"message_id": "older", "role": "assistant", "content": "SELECTED_OLDER_TEXT"}]})
    context.task_brief = {"message_refs": ["chosen"], "evidence_refs": [selected, history],
                          "resolved_references": [{"expression": "it", "meaning": "server alpha"}],
                          "uncertainties": ["Current status is unknown"]}

    projection = context.projection()
    assert [item["tool"] for item in projection["evidence"]] == ["file.read"]
    assert {item["message_id"] for item in projection["conversation_materials"]} == {"chosen", "older"}
    assert projection["conversation_materials"][0]["truncated"]
    assert "UNRELATED_ANSWER" not in json.dumps(projection)
    assert projection["uncertainties"] == ["Current status is unknown"]
    assert projection["resolved_references"][0]["meaning"] == "server alpha"


def test_planner_drops_legacy_chat_memory_but_preserves_own_memory_and_brief():
    request = PlanRequest(context=PlannerContext(
        goal="Check alpha", trigger="initial", execution_ledger={},
        memory_context=[{"type": "chat_context", "recent_anchor": {"assistant_outcome": "OLD_ANSWER"}},
                        {"type": "project_context", "keys": ["company"]},
                        {"kind": "fact", "subject": "timezone", "value": "UTC"},
                        {"type": "document_memory", "groups": [{"scope_slug": "company", "items": []}]}],
        task_brief={"goal": "Check alpha", "constraints": ["Read the actual source"]},
    ))
    payload = PlannerInputBuilder().build_graph_request(request)
    assert "OLD_ANSWER" not in json.dumps(payload)
    assert len(payload["memory_context"]) == 2
    assert payload["task_brief"]["constraints"] == ["Read the actual source"]


def test_agent_receives_task_inputs_and_dependencies_without_chat_transcript():
    task = TaskRequest(task_id="read", executor="reader", intent="Read current status",
                       instructions="Check server alpha", inputs={"server": "alpha"},
                       dependency_outputs={"lookup": {"answer": "SELECTED_DEPENDENCY"}})
    messages = AgentExecutor._build_sub_messages([
        {"role": "assistant", "content": "OLD_ASSISTANT_RESULT"},
        {"role": "user", "content": "OLD_USER_REQUEST"},
    ], task, "Check it")
    serialized = json.dumps(messages)
    assert "OLD_ASSISTANT_RESULT" not in serialized
    assert "OLD_USER_REQUEST" not in serialized
    assert "SELECTED_DEPENDENCY" in serialized
    assert "alpha" in serialized
    assert all(item["role"] == "user" for item in messages)


def test_explicit_history_read_replaces_truncated_recent_copy():
    context = RunContext(recent_dialogue=[{"message_id": "selected", "role": "assistant",
                                          "content": "Short", "truncated": True}])
    context.add_evidence("chat.history.read", {}, {"messages": [
        {"message_id": "selected", "role": "assistant", "content": "Short but now complete", "truncated": False}]})
    result = context.projection(message_refs=["selected"])["conversation_materials"][0]
    assert result["content"] == "Short but now complete"
    assert not result["truncated"]


def test_unknown_material_reference_does_not_become_a_successful_empty_read():
    projection = RunContext().projection(message_refs=["missing-message"], evidence_refs=["missing-source"])
    assert projection["unavailable_material_refs"] == ["missing-message", "missing-source"]
    assert projection["evidence"] == []
    assert projection["conversation_materials"] == []


@pytest.mark.asyncio
async def test_planner_resume_uses_saved_preflight_brief_instead_of_generic_continuation():
    from app.runtime.orchestrator import GraphOrchestrator
    run_id, plan_id = uuid4(), uuid4()
    brief = {"goal": "Check alpha", "constraints": ["Keep the user's constraint"],
             "resolved_references": [{"expression": "it", "meaning": "alpha"}], "message_refs": ["selected"]}
    state = SimpleNamespace(run_context=RunContext(task_brief=brief), attachment_contexts=[])
    orchestrator = object.__new__(GraphOrchestrator)
    orchestrator.store = SimpleNamespace(snapshot=AsyncMock(return_value={"root_run_id": str(run_id), "tasks": {}}))
    request = await orchestrator._planner_request(plan_id=plan_id, goal="Check alpha", trigger="resume",
        available_agents=[], available_artifacts=[], planner_kwargs={"runtime_state": state,
            "task_brief": {"goal": "Continue the checkpoint"}})
    assert request.context.task_brief == brief
