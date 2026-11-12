"""PostgreSQL checks for exact cross-run snapshot import and read semantics."""
from __future__ import annotations

import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.services.result_workspace import ResultWorkspace
from app.services.tool_result_store import ResultSnapshotUnavailable, ToolResultStore

pytestmark = pytest.mark.skipif(os.getenv("TOOL_WORKSPACE_PG") != "1", reason="requires isolated tool-results PostgreSQL")


@pytest_asyncio.fixture
async def isolated_results():
    schema = "test_cross_turn_" + uuid4().hex
    url = get_settings().TOOL_RESULTS_DB_URL
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}},
        json_deserializer=lambda value: json.loads(value, parse_float=Decimal))

    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            for number, filename in enumerate(("tool_payloads.py", "sql_result_rows.py",
                    "result_datasets.py", "virtual_table_rows.py", "nullable_source_complete.py"), 1):
                path = Path("app/tool_results_migrations/versions") / f"{number:04d}_{filename}"
                spec = importlib.util.spec_from_file_location(filename[:-3], path)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    from app.services import result_workspace, tool_result_store
    old_workspace_engine, old_store_engine = result_workspace.get_tool_results_engine, tool_result_store.get_tool_results_engine
    result_workspace.get_tool_results_engine = lambda: engine
    tool_result_store.get_tool_results_engine = lambda: engine
    yield engine, {"run_id": str(uuid4()), "tenant_id": uuid4(), "user_id": uuid4()}
    result_workspace.get_tool_results_engine, tool_result_store.get_tool_results_engine = old_workspace_engine, old_store_engine
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


@pytest.mark.asyncio
async def test_import_is_exact_idempotent_scoped_and_snapshot_only(isolated_results):
    engine, scope = isolated_results
    store = ToolResultStore()
    workspace = ResultWorkspace()
    source_run, target_run = str(uuid4()), str(uuid4())
    saved, _ = await workspace.save_source(payload={"rows": [
        {"id": 1, "profile": {"name": "Ada", "score": 9}},
        {"id": 2, "profile": {"name": "Lin", "score": 7}},
    ], "total": 2, "has_more": False}, source_tool="collection.search",
        arguments={"offset": 0, "limit": 2}, run_id=source_run, tenant_id=scope["tenant_id"],
        user_id=scope["user_id"], operation="collection.search", call_id="source",
        task_id="task", agent_execution_id="agent")
    async with engine.connect() as connection:
        source_expiry = (await connection.execute(text("SELECT expires_at FROM runtime_tool_payloads WHERE id=CAST(:id AS uuid)"),
                                                   {"id": saved["result_id"]})).scalar_one()

    imported = await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
        source_revision=saved["revision"], target_run_id=target_run, target_tenant_id=scope["tenant_id"],
        target_user_id=scope["user_id"], target_task_id="task-next", target_agent_execution_id="agent-next")
    again = await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
        source_revision=saved["revision"], target_run_id=target_run, target_tenant_id=scope["tenant_id"],
        target_user_id=scope["user_id"], target_task_id="task-next", target_agent_execution_id="agent-next")
    assert imported["result_id"] == again["result_id"]
    assert again["already_imported"] is True
    assert imported["snapshot_only"] is True
    assert imported["imported_from"]["source_run_id"] == source_run
    async with engine.connect() as connection:
        target_expiry = (await connection.execute(text("SELECT expires_at FROM runtime_tool_payloads WHERE id=CAST(:id AS uuid)"),
                                                   {"id": imported["result_id"]})).scalar_one()
    assert target_expiry == source_expiry

    visible = await workspace.read(result_id=imported["result_id"], run_id=target_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], offset=0, limit=2)
    assert visible["value"] == [
        {"id": 1, "profile": {"name": "Ada", "score": 9}},
        {"id": 2, "profile": {"name": "Lin", "score": 7}},
    ]
    assert visible["snapshot_only"] is True
    assert visible["imported_from"]["source_result_id"] == saved["result_id"]

    auto_view = await workspace.read(result_id=imported["result_id"], run_id=target_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], path="/profile", limit=1)
    assert auto_view["value"] == [{"name": "Ada", "score": 9}]
    assert auto_view["view"] == "auto"
    children_view = await workspace.read(result_id=imported["result_id"], run_id=target_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], path="/profile",
        view="children", child_limit=1, limit=1)
    from app.agents.context import ToolResult
    from app.agents.runtime.tools import OperationExecutionFacade
    formatted = json.loads(OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(children_view, workspace_view=True), operation_slug="result.read"))
    assert formatted["view"] == "children"
    next_args = formatted["next_action"]["arguments"]
    assert next_args["view"] == "children" and next_args["child_offset"] == 1
    next_children = await workspace.read(**next_args, run_id=target_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"])
    assert next_children["value"][0]["children"][0]["key"] == "score"

    catalog = await store.list_prior_snapshots(source_run_id=source_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], offset=0, limit=1)
    assert catalog["items"][0]["result_id"] == saved["result_id"]
    assert catalog["items"][0]["importable"] is True
    selected_catalog = await store.list_prior_snapshots(source_run_id=source_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], selected_result_ids=[
            saved["result_id"], str(uuid4())])
    assert selected_catalog["items"][0]["result_id"] == saved["result_id"]
    assert selected_catalog["items"][1]["unavailable_reason"] == "snapshot_unavailable"

    with pytest.raises(ResultSnapshotUnavailable):
        await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
            source_revision=saved["revision"] + 1, target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])
    with pytest.raises(ResultSnapshotUnavailable):
        await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
            source_revision=saved["revision"], target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=uuid4())
    with pytest.raises(ResultSnapshotUnavailable):
        await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
            source_revision=saved["revision"], target_run_id=str(uuid4()),
            target_tenant_id=uuid4(), target_user_id=scope["user_id"])

    file_source, _ = await workspace.save_source(payload={"text": "private artifact contents"},
        source_tool="file.read", arguments={"artifact_id": "opaque"}, run_id=source_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], operation="file.read",
        call_id="file-source", task_id="task", agent_execution_id="agent")
    with pytest.raises(ResultSnapshotUnavailable) as file_error:
        await store.import_snapshot(source_run_id=source_run, source_result_id=file_source["result_id"],
            source_revision=file_source["revision"], target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])
    assert file_error.value.reason == "source_reauthorization_required"

    with pytest.raises(ResultSnapshotUnavailable):
        await store.import_snapshot(source_run_id=source_run, source_result_id=saved["result_id"],
            source_revision=saved["revision"], target_run_id=source_run,
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])

    expired, _ = await workspace.save_source(payload={"rows": [{"ok": True}]},
        source_tool="collection.search", arguments={"offset": 0}, run_id=source_run,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], operation="collection.search",
        call_id="expired-source", task_id="task", agent_execution_id="agent")
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET expires_at=now()-interval '1 second' WHERE id=CAST(:id AS uuid)"),
                                 {"id": expired["result_id"]})
    with pytest.raises(ResultSnapshotUnavailable):
        await store.import_snapshot(source_run_id=source_run, source_result_id=expired["result_id"],
            source_revision=expired["revision"], target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])


@pytest.mark.asyncio
async def test_synthesis_preserves_distinct_nested_reader_views(isolated_results, monkeypatch):
    _, scope = isolated_results
    workspace = ResultWorkspace()
    saved, _ = await workspace.save_source(payload={"rows": [{"report": {"first": "abcdefgh",
        "second": "01234567"}}], "total": 1, "has_more": False}, source_tool="collection.search",
        arguments={"offset": 0, "limit": 1}, operation="collection.search", call_id="nested-views",
        task_id="task", agent_execution_id="agent", **scope)
    refs = [
        {"result_id": saved["result_id"], "operation": "result.read", "revision": saved["revision"],
         "reader_arguments": {"result_id": saved["result_id"], "revision": saved["revision"],
             "offset": 0, "limit": 1, "path": "/report/first", "text_offset": 0,
             "text_limit": 2, "view": "auto"},
         "observation": {"result_id": saved["result_id"], "revision": saved["revision"],
             "offset": 0, "limit": 1, "path": "/report/first", "text_offset": 0,
             "text_limit": 2, "view": "auto"}},
        {"result_id": saved["result_id"], "operation": "result.read", "revision": saved["revision"],
         "reader_arguments": {"result_id": saved["result_id"], "revision": saved["revision"],
             "offset": 0, "limit": 1, "path": "/report/first", "text_offset": 2,
             "text_limit": 2, "view": "auto"},
         "observation": {"result_id": saved["result_id"], "revision": saved["revision"],
             "offset": 0, "limit": 1, "path": "/report/first", "text_offset": 2,
             "text_limit": 2, "view": "auto"}},
    ]
    from app.runtime.synthesizer import Synthesizer
    selected = Synthesizer._selected_result_references([{"verified_result_refs": refs}], {})
    assert len(selected) == 2
    assert [item["text_offset"] for item in selected] == [0, 2]

    observed: list[dict] = []
    original_read = ResultWorkspace.read

    async def capture_read(self, **kwargs):
        observed.append({key: kwargs.get(key) for key in (
            "result_id", "revision", "offset", "limit", "path", "text_offset", "text_limit", "view")})
        return await original_read(self, **kwargs)

    monkeypatch.setattr(ResultWorkspace, "read", capture_read)
    catalog = await ToolResultStore().list_for_run(**scope)
    entry = next(item for item in catalog if item["result_id"] == saved["result_id"])
    pages, limitations = await Synthesizer._prepare_result_evidence(
        references=selected, catalog_by_id={saved["result_id"]: entry},
        ctx=SimpleNamespace(user_id=scope["user_id"], tenant_id=scope["tenant_id"]),
        run_id=scope["run_id"])
    assert [item["code"] for item in limitations] == [
        "selected_result_page_partial", "selected_result_page_partial"]
    assert len(pages) == 2
    assert [item["records"][0] for item in pages] == ["ab", "cd"]
    assert [item["text_offset"] for item in observed] == [0, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [
    "collection.doc_search", "collection.list_documents", "instance.collection.doc_search",
    "instance_collection_doc_search", "collection_doc_search", "collection.list.documents",
    "memory.search", "instance.memory_search", "file.read", "artifact.fetch",
])
async def test_file_controlled_operations_are_never_cross_turn_importable(isolated_results, operation):
    store, workspace = ToolResultStore(), ResultWorkspace()
    run_id = str(uuid4())
    scope = {**isolated_results[1], "run_id": run_id}
    saved, _ = await workspace.save_source(payload={"items": [{"text": "private"}]},
        source_tool=operation, arguments={}, operation=operation,
        call_id=f"unsafe-{operation}", task_id="task", agent_execution_id="agent", **scope)

    catalog = await store.list_prior_snapshots(source_run_id=run_id, selected_result_ids=[saved["result_id"]],
        tenant_id=scope["tenant_id"], user_id=scope["user_id"])
    assert catalog["items"][0]["importable"] is False
    assert catalog["items"][0]["unavailable_reason"] == "source_reauthorization_required"
    with pytest.raises(ResultSnapshotUnavailable, match="source_reauthorization_required"):
        await store.import_snapshot(source_run_id=run_id, source_result_id=saved["result_id"],
            source_revision=saved["revision"], target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])


@pytest.mark.asyncio
async def test_sql_lineage_checks_all_sources_beyond_fifty(isolated_results):
    _, scope = isolated_results
    workspace, store = ResultWorkspace(), ToolResultStore()
    run_id = str(uuid4())
    scope = {**scope, "run_id": run_id}
    file_source, _ = await workspace.save_source(payload=[{"id": -1}], source_tool="file.read",
        arguments={}, operation="file.read", call_id="file-source-first",
        task_id="task", agent_execution_id="agent", **scope)
    safe_sources = []
    for index in range(50):
        saved, _ = await workspace.save_source(payload={"rows": [{"id": index}]}, source_tool="collection.search",
            arguments={}, operation="collection.search", call_id=f"safe-source-{index}",
            task_id="task", agent_execution_id="agent", **scope)
        safe_sources.append(saved)

    query = " UNION ALL ".join(
        f"SELECT * FROM result_{item['result_id'].replace('-', '')}"
        for item in [*safe_sources, file_source]
    )
    derived = await store.execute_sql(sql=query, run_id=run_id, tenant_id=scope["tenant_id"],
        user_id=scope["user_id"], call_id="union-51", task_id="task", agent_execution_id="agent")
    assert len(derived["source_result_ids"]) == 51
    assert file_source["result_id"] in derived["source_result_ids"]
    lineage_with_file_last = [item for item in derived["source_result_ids"]
                              if item != file_source["result_id"]] + [file_source["result_id"]]
    async with isolated_results[0].begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": derived["result_id"], "ids": json.dumps(lineage_with_file_last)})
    catalog = await store.list_prior_snapshots(source_run_id=run_id,
        selected_result_ids=[derived["result_id"]], tenant_id=scope["tenant_id"], user_id=scope["user_id"])
    assert catalog["items"][0]["importable"] is False
    with pytest.raises(ResultSnapshotUnavailable, match="source_reauthorization_required"):
        await store.import_snapshot(source_run_id=run_id, source_result_id=derived["result_id"],
            source_revision=derived["_stored_result"]["revision"], target_run_id=str(uuid4()),
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])


@pytest.mark.asyncio
async def test_lineage_fails_closed_for_corruption_missing_cycle_and_allows_shared_ancestor(isolated_results):
    engine, scope = isolated_results
    workspace, store = ResultWorkspace(), ToolResultStore()
    run_id = str(uuid4())
    scope = {**scope, "run_id": run_id}

    async def save(call_id: str):
        return (await workspace.save_source(payload={"rows": [{"id": call_id}]}, source_tool="collection.search",
            arguments={}, operation="collection.search", call_id=call_id,
            task_id="task", agent_execution_id="agent", **scope))[0]

    malformed, missing, cyclic, metadata_hidden = (
        await save("malformed"), await save("missing"), await save("cyclic"), await save("metadata-hidden"))
    left, right, shared, root = await save("left"), await save("right"), await save("shared"), await save("root")
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids='{}'::jsonb WHERE id=CAST(:id AS uuid)"),
                                 {"id": malformed["result_id"]})
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": missing["result_id"], "ids": json.dumps([str(uuid4())])})
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": cyclic["result_id"], "ids": json.dumps([cyclic["result_id"]])})
        await connection.execute(text("UPDATE runtime_tool_payloads SET dataset_meta=CAST(:meta AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": metadata_hidden["result_id"], "meta": json.dumps({"source_result_ids": [missing["result_id"]]})})
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": left["result_id"], "ids": json.dumps([shared["result_id"]])})
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": right["result_id"], "ids": json.dumps([shared["result_id"]])})
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": root["result_id"], "ids": json.dumps([left["result_id"], right["result_id"]])})

    selected_ids = [malformed["result_id"], missing["result_id"], cyclic["result_id"],
                    metadata_hidden["result_id"], root["result_id"]]
    catalog = await store.list_prior_snapshots(source_run_id=run_id, selected_result_ids=selected_ids,
        tenant_id=scope["tenant_id"], user_id=scope["user_id"])
    by_id = {item["result_id"]: item for item in catalog["items"]}
    assert by_id[malformed["result_id"]]["importable"] is False
    assert by_id[missing["result_id"]]["importable"] is False
    assert by_id[cyclic["result_id"]]["importable"] is False
    assert by_id[metadata_hidden["result_id"]]["importable"] is False
    assert by_id[root["result_id"]]["importable"] is True


@pytest.mark.asyncio
async def test_imported_snapshot_rechecks_source_lineage_on_import_of_import(isolated_results):
    engine, scope = isolated_results
    workspace, store = ResultWorkspace(), ToolResultStore()
    source_run, middle_run, target_run = str(uuid4()), str(uuid4()), str(uuid4())
    scope = {**scope, "run_id": source_run}
    upstream, _ = await workspace.save_source(payload={"rows": [{"id": 1}]}, source_tool="collection.search",
        arguments={}, operation="collection.search", call_id="upstream", task_id="task",
        agent_execution_id="agent", **scope)
    derived, _ = await workspace.save_source(payload={"rows": [{"id": 1}]}, source_tool="collection.search",
        arguments={}, operation="collection.search", call_id="derived", task_id="task",
        agent_execution_id="agent", **scope)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": derived["result_id"], "ids": json.dumps([upstream["result_id"]])})
    imported = await store.import_snapshot(source_run_id=source_run, source_result_id=derived["result_id"],
        source_revision=derived["revision"], target_run_id=middle_run,
        target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])
    assert imported["imported_from"]["source_result_ids"] == [upstream["result_id"]]

    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET operation='file.read' WHERE id=CAST(:id AS uuid)"),
            {"id": upstream["result_id"]})
    with pytest.raises(ResultSnapshotUnavailable, match="source_reauthorization_required"):
        await store.import_snapshot(source_run_id=middle_run, source_result_id=imported["result_id"],
            source_revision=imported["revision"], target_run_id=target_run,
            target_tenant_id=scope["tenant_id"], target_user_id=scope["user_id"])


@pytest.mark.asyncio
async def test_lineage_budget_exhaustion_is_explicitly_unavailable(isolated_results, monkeypatch):
    engine, scope = isolated_results
    workspace, store = ResultWorkspace(), ToolResultStore()
    run_id = str(uuid4())
    scope = {**scope, "run_id": run_id}
    source, _ = await workspace.save_source(payload={"rows": [{"id": 1}]}, source_tool="collection.search",
        arguments={}, operation="collection.search", call_id="source", task_id="task",
        agent_execution_id="agent", **scope)
    derived, _ = await workspace.save_source(payload={"rows": [{"id": 1}]}, source_tool="collection.search",
        arguments={}, operation="collection.search", call_id="derived", task_id="task",
        agent_execution_id="agent", **scope)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_result_ids=CAST(:ids AS jsonb) WHERE id=CAST(:id AS uuid)"),
            {"id": derived["result_id"], "ids": json.dumps([source["result_id"]])})
    from app.services import tool_result_store as store_module
    settings = get_settings()
    monkeypatch.setattr(store_module, "get_settings", lambda: type("Settings", (), {
        "TOOL_RESULTS_LINEAGE_MAX_NODES": 1,
        "TOOL_RESULTS_LINEAGE_MAX_DEPTH": settings.TOOL_RESULTS_LINEAGE_MAX_DEPTH,
    })())
    catalog = await store.list_prior_snapshots(source_run_id=run_id, selected_result_ids=[derived["result_id"]],
        tenant_id=scope["tenant_id"], user_id=scope["user_id"])
    assert catalog["items"][0]["importable"] is False
