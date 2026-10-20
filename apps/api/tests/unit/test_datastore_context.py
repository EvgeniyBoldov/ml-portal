"""Role inventories must preserve references without leaking source contents."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.runtime.datastore_context import (
    build_datastore, file_metadata, load_result_catalog, result_references, task_files,
)
from app.services.tool_result_store import _profile_rows


def dataset(result_id="r1", task_id="producer"):
    schema, *_ = _profile_rows([{"id": 1, "details": {"value": "PRIVATE_DATA"}}])
    return {"result_id": result_id, "task_id": task_id, "call_id": "call-1",
            "agent_execution_id": "attempt-1", "operation": "api.search", "row_count": 1,
            "source_complete": False, "revision": 2, "observed_schema": schema,
            "sql_ref": "result_" + result_id, "sample": [{"details": "PRIVATE_DATA"}],
            "dataset_meta": {"next_arguments": {"token": "PRIVATE_ARGUMENTS"}}}


def test_inventory_has_metadata_and_provenance_without_payloads_or_journal():
    value = build_datastore(files=[{
        "artifact_id": "f1", "artifact": {
            "artifact_id": "f1", "file": {"name": "report.pdf", "size_bytes": 0},
            "origin": {"kind": "user_upload", "source_id": "attachment-1", "text": "PRIVATE_FILE"},
            "description": {"text": "Annual report", "source": "source_metadata"},
            "representation": {"id": "v1", "status": "partial"},
            "attributes": {"content": "PRIVATE_FILE"},
        }, "snippet": "PRIVATE_FILE", "content": "PRIVATE_FILE",
        "journal": "PRIVATE_TRACE",
    }], results=[dataset()])
    file, result = value["items"]
    assert file["size_bytes"] == 0
    assert file["representation_status"] == "partial"
    assert file["origin"]["source_id"] == "attachment-1"
    assert result["producer"]["task_id"] == "producer"
    assert result["revision"] == 2 and result["source_complete"] is False
    assert result["sql_columns"]["details"]["type"] == "jsonb"
    assert "PRIVATE_" not in json.dumps(value)


def test_files_deduplicate_and_keep_current_status_when_supplemented_by_source():
    files = file_metadata([
        {"ref": {"artifact_id": "f1", "file_name": "report.pdf"},
         "is_current": True, "snippet_status": "partial", "representation_id": "v1"},
        {"artifact_id": "f1", "artifact": {"origin": {"kind": "rag_document", "source_id": "doc-1"}}},
    ])
    assert len(files) == 1
    assert files[0]["is_current"] is True
    assert files[0]["representation_id"] == "v1"
    assert files[0]["representation_status"] == "partial"


def test_task_inventory_contains_own_dependencies_and_explicit_refs_only():
    value = build_datastore(results=[dataset("own", "consumer"), dataset("dep", "producer"),
        dataset("explicit", "other"), dataset("hidden", "sibling")],
        task_ids={"consumer", "producer"}, result_ids={"explicit"})
    assert [item["result_id"] for item in value["items"]] == ["own", "dep", "explicit"]
    assert build_datastore(results=[dataset()], task_ids=set())["items"] == []
    assert len(build_datastore(results=[dataset(str(i)) for i in range(15)])["items"]) == 15


def test_only_explicit_files_are_collected_and_deleted_files_are_omitted():
    results = [{"attachments": [{"artifact_id": "generated"}],
        "sources": [{"artifact_id": "source"}],
        "structured_response": {"artifact_id": "unverified"}},
        {"verified": {"artifacts": [{"artifact_id": "legacy"}]}}]
    value = build_datastore(files=task_files(results), deleted_artifact_ids={"generated"})
    assert [item["artifact_id"] for item in value["items"]] == ["source", "legacy"]


def test_explicit_dataset_references_survive_nested_dependency_values():
    assert result_references({"inputs": [{"result_id": "r1"}], "other": {"id": "not-a-ref"}}) == {"r1"}


@pytest.mark.asyncio
async def test_catalog_outage_is_explicit_and_absent_context_does_not_query(monkeypatch):
    load = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr("app.services.tool_result_store.ToolResultStore.list_for_run", load)
    ctx = SimpleNamespace(user_id="u", tenant_id="t")
    assert await load_result_catalog(ctx=ctx, run_id="run") == ([], "unavailable")
    load.assert_awaited_once_with(run_id="run", user_id="u", tenant_id="t")
    load.reset_mock()
    assert await load_result_catalog(ctx=None, run_id="run") == ([], "not_requested")
    load.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", [False, True])
async def test_agent_llm_receives_one_current_inventory_with_own_and_dependency_results(monkeypatch, resumed):
    from uuid import uuid4
    from app.agents.runtime import agent as module
    from app.agents.runtime.agent import AgentToolRuntime
    from app.agents.runtime.policy import GenerationParams, PolicyLimits
    from app.services.runtime_event_logger import RuntimeLoggingLevel

    catalog = [dataset("own", "consumer"), dataset("dependency", "producer"), dataset("hidden", "sibling")]
    monkeypatch.setattr("app.runtime.datastore_context.load_result_catalog",
                        AsyncMock(return_value=(catalog, "available")))
    runtime = AgentToolRuntime(Mock())
    runtime.llm.call = AsyncMock(return_value='{"completion":"fulfilled","answer":"Done"}')
    runtime.config_resolver.resolve = AsyncMock(return_value=(
        PolicyLimits(max_llm_calls=2), GenerationParams(model="test"),
        {"native_tool_calling": False}, SimpleNamespace(sources={})))
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=RuntimeLoggingLevel.NONE)
    runtime.prompt_assembler.assemble = Mock(return_value=SimpleNamespace(system_prompt="Test"))
    runtime._create_run_session = Mock(return_value=SimpleNamespace(
        run_id=uuid4(), start=AsyncMock(), record_event=AsyncMock(), finish=AsyncMock()))
    monkeypatch.setattr(module, "serialize_published_operations", lambda operations: [])
    monkeypatch.setattr(module, "serialize_published_collections", lambda *args: [])
    deps = SimpleNamespace(sandbox_overrides={}, resolved_operations=[])
    extra = {"runtime_root_run_id": str(uuid4()), "runtime_task_id": "consumer",
             "runtime_datastore_task_ids": ["consumer", "producer"],
             "runtime_datastore_files": [{"ref": {"artifact_id": "input", "file_name": "input.pdf"},
                                          "snippet": "PRIVATE_FILE"}]}
    if resumed:
        extra["interaction_resume_checkpoint"] = {"messages": [{"role": "user", "content":
            '[Datastore — available file and result metadata]\n{"items":[{"result_id":"STALE"}]}'}]}
    ctx = SimpleNamespace(extra=extra, get_runtime_deps=lambda: deps,
                          set_runtime_deps=lambda value: None, log_intent=AsyncMock())
    request = SimpleNamespace(agent=SimpleNamespace(slug="research"), resolved_operations=[],
        resolved_data_instances=[], rbac_audit={}, partial_mode_warning=None, run_id=uuid4())
    _ = [event async for event in runtime.execute(request, [{"role": "user", "content": "Review"}], ctx)]
    messages = runtime.llm.call.await_args.kwargs["messages"]
    inventories = [item["content"] for item in messages if item.get("content", "").startswith("[Datastore")]
    assert len(inventories) == 1
    inventory = json.loads(inventories[0].split("\n", 1)[1])
    assert [item.get("artifact_id") or item.get("result_id") for item in inventory["items"]] == [
        "input", "own", "dependency"]
    assert "PRIVATE_" not in inventories[0] and "STALE" not in inventories[0]
