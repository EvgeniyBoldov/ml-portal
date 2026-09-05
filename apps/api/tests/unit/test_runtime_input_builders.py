from __future__ import annotations

import json
from uuid import uuid4
from types import SimpleNamespace

from app.runtime.input_builders import PlannerInputBuilder, SynthesizerInputBuilder
from app.runtime.orchestrator_contracts import PlanRequest
from app.runtime.contracts import AttachmentContext, AttachmentRef
from app.runtime.memory.components import MemoryBundle
from app.runtime.turn_state import RuntimeTurnState


def _memory():
    return SimpleNamespace(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="legacy goal",
        question="legacy q",
        status="running",
        memory_state={},
    )


def test_planner_input_builder_prefers_runtime_turn_state_snapshot():
    memory = _memory()
    state = RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal="canonical goal",
        current_user_query="canonical q",
        memory_bundle=MemoryBundle(),
    )
    state.add_runtime_fact("runtime fact")
    memory.memory_state["runtime_turn_state"] = state.model_dump(mode="json")

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[{"slug": "a", "description": "agent"}],
        outline=None,
        platform_config={},
    )
    assert payload["goal"] == "canonical goal"
    assert payload["current_user_query"] == "canonical q"
    assert payload["memory"]["facts"] == ["runtime fact"]
    assert payload["available_agents"] == [
        {
            "slug": "a",
            "description": "agent",
            "tags": [],
            "provides_keys": [],
        }
    ]


def test_graph_planner_input_builder_uses_persisted_plan_contract():
    payload = PlannerInputBuilder().build_graph_request(PlanRequest(
        goal="Проверить конфигурацию",
        trigger="technical_failure",
        plan={"revision": 2, "tasks": {}, "outputs": {}},
        completed_outputs={"inspect": {"status": "completed"}},
        needs=[{"key": "credential"}],
        last_failure={"code": "timeout"},
        available_agents=[{"slug": "viewer", "description": "Просмотр данных"}],
    ))

    assert set(payload) == {
        "goal", "mode", "replan_reason", "plan", "available_artifacts",
        "needs", "last_failure", "completed_outputs", "memory_context", "available_agents",
        "terminal_synthesis",
    }
    assert payload["mode"] == "replan"
    assert payload["replan_reason"] == "technical_failure"
    assert payload["available_artifacts"] == []
    assert payload["available_agents"] == [{
        "slug": "viewer", "description": "Просмотр данных", "tags": [], "provides_keys": [],
    }]
    assert payload["completed_outputs"] == {"inspect": {"status": "completed"}}
    assert payload["terminal_synthesis"]["kind"] == "synthesis"


def test_graph_planner_input_builder_normalizes_artifact_contexts():
    payload = PlannerInputBuilder().build_graph_request(PlanRequest(
        goal="Прочитать файл",
        trigger="initial",
        plan={"revision": 0, "tasks": {}},
        available_artifacts=[{
            "ref": {"artifact_id": "artifact-1", "file_name": "notes.txt", "content_type": "text/plain"},
            "snippet": "hello",
            "snippet_status": "ready",
            "readable": True,
        }],
    ))

    assert payload["available_artifacts"] == [{
        "artifact_id": "artifact-1",
        "file_name": "notes.txt",
        "content_type": "text/plain",
        "size_bytes": None,
        "snippet": "hello",
        "snippet_status": "ready",
        "readable": True,
        "truncated": False,
    }]


def test_planner_input_builder_includes_structured_continuation():
    state = RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="original goal",
        current_user_query="[confirmation]",
        memory_bundle=MemoryBundle(),
        continuation={
            "mode": "resume",
            "resume_action": "confirm",
            "original_goal": "original goal",
            "paused_context": {"question": "Выполнить опасную операцию?"},
            "user_response": "[confirmation]",
        },
    )

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[],
        outline=None,
        platform_config={},
    )

    assert payload["continuation"]["mode"] == "resume"
    assert payload["continuation"]["resume_action"] == "confirm"
    assert payload["continuation"]["original_goal"] == "original goal"


def test_planner_input_builder_includes_attachment_contexts():
    state = RuntimeTurnState.from_seed(
        run_id=uuid4(),
        chat_id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        goal="inspect file",
        current_user_query="what is in the file?",
        memory_bundle=MemoryBundle(),
        attachment_contexts=[
            AttachmentContext(
                ref=AttachmentRef(
                    artifact_id="artifact-1",
                    file_name="notes.txt",
                ),
                snippet="hello world",
                snippet_status="ready",
                readable=True,
            )
        ],
    )

    payload = PlannerInputBuilder().build(
        runtime_state=state,
        available_agents=[],
        outline=None,
        platform_config={},
    )

    assert payload["attachments"] == [
        {
            "file_name": "notes.txt",
            "artifact_id": "artifact-1",
            "content_type": None,
            "size_bytes": None,
            "snippet": "hello world",
            "snippet_status": "ready",
            "readable": True,
            "truncated": False,
        }
    ]


def test_synthesizer_input_builder_serializes_only_the_prebuilt_context():
    context = {
        "synthesis_task": {"task_id": "answer", "intent": "Answer the request", "instructions": "Be concise"},
        "completed_task_reports": [{"task_id": "inspect", "report": {"description": "Found it"}}],
        "artifacts": [{"artifact_id": "artifact-1", "file_name": "example.txt"}],
        "sources": [{"source_id": "doc-1", "source_name": "Doc One"}],
    }
    messages = SynthesizerInputBuilder().build(
        synthesis_context=context,
        system_prompt="sys",
    )
    assert messages[0]["content"] == "sys"
    payload = json.loads(messages[1]["content"])
    assert payload == context
