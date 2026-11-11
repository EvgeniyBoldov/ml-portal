"""Opt-in real PostgreSQL dataset lifecycle in an isolated schema."""
import importlib.util
import json
import os
from pathlib import Path
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.services.result_workspace import ResultWorkspace
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError

pytestmark = pytest.mark.skipif(os.getenv("TOOL_WORKSPACE_PG") != "1", reason="requires tool-results PostgreSQL")


@pytest_asyncio.fixture
async def workspace_pg(monkeypatch):
    name = "test_workspace_" + uuid4().hex
    url = get_settings().TOOL_RESULTS_DB_URL
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{name}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": name}},
        json_deserializer=lambda value: json.loads(value, parse_float=Decimal))
    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            for filename in ("0001_tool_payloads.py", "0002_sql_result_rows.py", "0003_result_datasets.py", "0004_virtual_table_rows.py"):
                path = Path("app/tool_results_migrations/versions") / filename
                spec = importlib.util.spec_from_file_location(filename[:-3], path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()
    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    monkeypatch.setattr("app.services.tool_result_store.get_tool_results_engine", lambda: engine)
    monkeypatch.setattr("app.services.result_workspace.get_tool_results_engine", lambda: engine)
    yield ResultWorkspace(), {"run_id": "test-" + uuid4().hex, "tenant_id": uuid4(), "user_id": uuid4()}, engine
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    await admin.dispose()


async def save(workspace, scope, *, call="first", items=None, total=3, next_page=True):
    return await workspace.save_source(payload={"count": total, "results": items if items is not None else [{"id": 1, "name": "a", "site": {"name": "EVN"}}],
        "next": "https://netbox/api/?offset=1&limit=1" if next_page else None},
        source_tool="netbox_get_objects", arguments={"object_type": "dcim.device", "limit": 1},
        operation="netbox_get_objects", call_id=call, task_id="task", agent_execution_id="agent", **scope)


@pytest.mark.asyncio
async def test_oversized_nested_record_can_be_projected_and_delivered_to_model(workspace_pg):
    import json
    from app.agents.context import ToolResult
    from app.agents.runtime.tools import OperationExecutionFacade

    workspace, scope, _ = workspace_pg
    fields = {"name": "Настройка сети", "description": "Работы " * 80,
              "status": {"name": "Open"}, "type": {"name": "Task"},
              "comments": None, "history": "я" * 5000}
    saved, _ = await workspace.save_source(payload={"fields": fields}, source_tool="external.get_record",
        arguments={}, operation="external.get_record", call_id="source", task_id="read",
        agent_execution_id="agent", **scope)
    read = await workspace.read(result_id=saved["result_id"], fields=["fields"], **scope)
    assert read["record_too_large"] and read["value"] == []
    output = await ToolResultStore().execute_sql(
        sql=("SELECT fields->>'name' AS name, fields->>'description' AS description, "
             "fields->'status'->>'name' AS status, fields->'type'->>'name' AS type, "
             f"fields->'comments' AS comments FROM {saved['sql_ref']}"),
        call_id="projection", task_id="read", agent_execution_id="agent", **scope)
    stored = output.pop("_stored_result")
    rendered = OperationExecutionFacade.format_result_for_context(ToolResult.ok(output), stored_result=stored)
    view = json.loads(rendered)
    assert view["records"] == [{"name": fields["name"], "description": fields["description"],
                              "status": "Open", "type": "Task", "comments": None}]
    assert view["source_coverage"]["complete"] is False
    assert len(rendered.encode()) <= get_settings().TOOL_RESULTS_CONTEXT_TOKENS * 3


@pytest.mark.asyncio
async def test_datastore_inventory_uses_real_catalog_provenance_and_scope(workspace_pg):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.agents.context import ToolContext
    from app.runtime.datastore_context import build_datastore
    from app.runtime.input_builders import PlannerInputBuilder
    from app.runtime.orchestrator import GraphOrchestrator

    _, scope, engine = workspace_pg
    # Use a UUID run identity, as required by the planner request contract.
    scope = {**scope, "run_id": str(uuid4())}
    store = ToolResultStore()
    async def create(call, task, **overrides):
        return await store.save(**{**scope, **overrides}, call_id=call, operation="api.list",
            task_id=task, agent_execution_id="attempt-" + task, payload=[{"name": "PRIVATE_ROW"}])
    own = await create("own", "consumer")
    dependency = await create("dependency", "producer")
    await create("sibling", "sibling")
    await create("different-user", "consumer", user_id=uuid4())
    await create("different-tenant", "consumer", tenant_id=uuid4())
    await create("different-run", "consumer", run_id=str(uuid4()))
    expired = await create("expired", "consumer")
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET expires_at=now()-interval '1 second' WHERE id=CAST(:id AS uuid)"),
                                 {"id": expired["result_id"]})
    catalog = await store.list_for_run(**scope)
    assert len(catalog) == 3
    assert catalog[0]["task_id"] == "consumer"
    assert catalog[0]["call_id"] == "own"
    assert catalog[0]["agent_execution_id"] == "attempt-consumer"
    files = [{"artifact_id": "input", "file_name": "source.pdf", "snippet": "PRIVATE_FILE"}]
    consumer = build_datastore(files=files, results=catalog, task_ids={"consumer", "producer"})
    assert [item.get("result_id") for item in consumer["items"] if item["kind"] == "result"] == [
        own["result_id"], dependency["result_id"]]
    import json
    assert "PRIVATE_" not in json.dumps(consumer)

    snapshot = {"root_run_id": scope["run_id"], "tasks": {}, "memory_context": [], "status": "active"}
    orchestrator = GraphOrchestrator(store=SimpleNamespace(snapshot=AsyncMock(return_value=snapshot)),
                                    planner=None, executor=None)
    request = await orchestrator._planner_request(plan_id=uuid4(), goal="Review", trigger="task_outcome",
        available_agents=[], available_artifacts=files, planner_kwargs={"ctx": ToolContext(
            user_id=scope["user_id"], tenant_id=scope["tenant_id"])})
    planner_inventory = PlannerInputBuilder().build_graph_request(request)["datastore"]
    assert len([item for item in planner_inventory["items"] if item["kind"] == "result"]) == 3
    assert planner_inventory["results_status"] == "available"


@pytest.mark.asyncio
async def test_datastore_prompt_migration_preserves_custom_rules_and_other_roles(workspace_pg):
    _, _, engine = workspace_pg
    path = Path("app/migrations/versions/0196_datastore_prompt_inventory.py")
    spec = importlib.util.spec_from_file_location("datastore_prompt_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    old = "CUSTOM: available_artifacts содержит паспорта доступных вложений: artifact_id. CUSTOM END"
    async with engine.begin() as connection:
        await connection.execute(text("""CREATE TABLE system_llm_roles
            (role_type text, rules text, is_active boolean, updated_at timestamptz)"""))
        await connection.execute(text("""INSERT INTO system_llm_roles VALUES
            ('turn_preflight', :rules, true, now()), ('planner', :rules, true, now()),
            ('turn_preflight', :rules, false, now())"""), {"rules": old})
        def migrate(sync_connection, fn):
            with Operations.context(MigrationContext.configure(sync_connection)):
                fn()
        await connection.run_sync(lambda sync: migrate(sync, migration.upgrade))
        rows = (await connection.execute(text("SELECT role_type, rules, is_active FROM system_llm_roles"))).all()
        assert sum("datastore.items" in row.rules for row in rows) == 1
        active = next(row.rules for row in rows if row.role_type == "turn_preflight" and row.is_active)
        assert active.startswith("CUSTOM: ") and active.endswith("CUSTOM END")
        await connection.run_sync(lambda sync: migrate(sync, migration.downgrade))
        assert set((await connection.execute(text("SELECT rules FROM system_llm_roles"))).scalars()) == {old}


@pytest.mark.asyncio
async def test_pages_share_identity_read_sql_and_access(workspace_pg):
    workspace, scope, engine = workspace_pg
    saved, _ = await save(workspace, scope)
    ref = {**scope, "result_id": saved["result_id"]}
    state = await workspace.state(**ref)
    args = state["dataset_meta"]["next_arguments"]
    payload = {"count": 3, "results": [{"id": 2, "name": "b", "site": {"name": "EVN"}}, {"id": 3, "name": "c", "ip": None}], "next": None}
    await workspace.append_page(payload=payload, source_tool="netbox_get_objects", arguments=args,
        expected_revision=1, call_id="second", **ref)
    duplicate = await workspace.append_page(payload=payload, source_tool="netbox_get_objects", arguments=args,
        expected_revision=1, call_id="retry", **ref)
    assert duplicate == {"appended": False, "revision": 2}
    page = await workspace.read(limit=1, fields=["name", "ip"], **ref)
    assert page["value"] == [{"name": "a", "ip": None}] and page["next_offset"] == 1
    assert page["revision"] == 2 and page["source_complete"]
    with pytest.raises(ToolResultStoreError, match="revision"):
        await workspace.read(revision=1, **ref)
    with pytest.raises(ToolResultStoreError, match="not found"):
        await workspace.describe(**{**ref, "user_id": uuid4()})
    sql = await ToolResultStore().execute_sql(sql=f"SELECT name, site->>'name' AS site_name FROM {saved['sql_ref']} ORDER BY name",
        call_id="query", task_id="task", agent_execution_id="agent", **scope)
    assert sql["rows"][0] == {"name": "a", "site_name": "EVN"}
    assert sql["row_count"] == 3
    assert sql["_stored_result"]["dataset_meta"]["input_revisions"] == {saved["result_id"]: 2}
    assert sql["result_id"] != saved["result_id"]


@pytest.mark.asyncio
async def test_read_projection_survives_formatter_and_next_page(workspace_pg):
    """A projected page receipt must be sufficient to read the next page."""
    from app.agents.context import ToolResult
    from app.agents.runtime.tools import OperationExecutionFacade

    workspace, scope, _ = workspace_pg
    saved, _ = await save(workspace, scope, items=[
        {"id": 1, "name": "first", "large": "x" * 5000},
        {"id": 2, "name": "second", "large": "y" * 5000},
        {"id": 3, "name": "third", "large": "z" * 5000},
    ], total=3, next_page=False)
    first = await workspace.read(result_id=saved["result_id"], fields=["id", "name"], limit=1, **scope)
    first_view = json.loads(OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(first, workspace_view=True), operation_slug="result.read"))
    next_args = first_view["next_action"]["arguments"]
    assert next_args == {"result_id": saved["result_id"], "revision": 1, "offset": 1,
                         "limit": 10, "fields": ["id", "name"]}

    second = await workspace.read(**next_args, **scope)
    assert second["value"] == [{"id": 2, "name": "second"}, {"id": 3, "name": "third"}]
    assert second["requested_fields"] == ["id", "name"]
    assert "large" not in json.dumps(second["value"])


@pytest.mark.asyncio
async def test_batch_total_reader_candidate_preserves_large_first_rows_for_final_projection(workspace_pg):
    from app.agents.context import ToolCall, ToolResult
    from app.agents.protocol import build_tool_result_messages
    from app.agents.runtime.model_context import reallocate_result_batch
    from app.adapters.impl.llm_context import estimate_request_tokens
    from app.agents.runtime.tools import OperationExecutionFacade

    workspace, scope, _ = workspace_pg
    large, _ = await save(workspace, scope, call="batch-large", items=[
        {"id": index, "text": f"large row {index} " + "x" * 2_000} for index in range(8)
    ], total=8, next_page=False)
    small, _ = await save(workspace, scope, call="batch-small", items=[{"id": 1, "text": "tiny"}],
                          total=1, next_page=False)
    batch_budget = 4_000
    old_equal_share = await workspace.read(result_id=large["result_id"], fields=["id", "text"],
        limit=20, context_budget_tokens=batch_budget // 2, context_model="gpt-4o-mini", **scope)
    candidate_large = await workspace.read(result_id=large["result_id"], fields=["id", "text"],
        limit=20, context_budget_tokens=batch_budget, context_model="gpt-4o-mini", **scope)
    candidate_small = await workspace.read(result_id=small["result_id"], fields=["id", "text"],
        limit=20, context_budget_tokens=batch_budget, context_model="gpt-4o-mini", **scope)
    assert len(old_equal_share["value"]) < 8
    assert len(candidate_large["value"]) == 8
    assert len(candidate_small["value"]) == 1

    calls = [ToolCall(id="large-call", tool_name="result.read", arguments={}),
             ToolCall(id="small-call", tool_name="result.read", arguments={})]
    entries = [
        {"call": calls[0], "call_id": calls[0].id, "result": ToolResult.ok(candidate_large, workspace_view=True),
         "stored_result": None, "evidence_call_id": calls[0].id},
        {"call": calls[1], "call_id": calls[1].id, "result": ToolResult.ok(candidate_small, workspace_view=True),
         "stored_result": None, "evidence_call_id": calls[1].id},
    ]

    def format_item(item, budget):
        return OperationExecutionFacade.format_result_for_context(item["result"],
            operation_slug="result.read", context_budget_tokens=budget, context_model="gpt-4o-mini")

    full = [format_item(item, batch_budget) for item in entries]
    used = sum(estimate_request_tokens({"model": "gpt-4o-mini", "messages": [
        {"role": "tool", "content": text}]}) for text in full)
    raw_calls = [{"id": item["call"].id, "function": {"name": "result.read"}} for item in entries]

    def request(texts):
        return {"model": "gpt-4o-mini", "messages": [
            {"role": "assistant", "tool_calls": raw_calls},
            *build_tool_result_messages([(item["call"], text) for item, text in zip(entries, texts)], raw_calls)]}

    assert used <= batch_budget
    allocation = reallocate_result_batch(entries, total_budget_tokens=batch_budget,
        model="gpt-4o-mini", format_item=format_item, request_for_texts=request, context_window_tokens=8192)
    assert allocation.fits_request
    projected = [json.loads(value) for value in allocation.texts]
    assert len(projected[0]["records"]) == 8
    assert projected[0]["records"][-1]["id"] == 7
    assert [item["tool_call_id"] for item in request(allocation.texts)["messages"][1:]] == [
        "large-call", "small-call"]


@pytest.mark.asyncio
async def test_synthesis_prepares_only_authorized_selected_saved_results(workspace_pg):
    from types import SimpleNamespace
    from app.runtime.synthesizer import Synthesizer

    workspace, scope, _ = workspace_pg
    saved, _ = await save(workspace, scope, items=[
        {"id": index, "name": f"row-{index}"} for index in range(7)
    ], total=7, next_page=False)
    catalog = await ToolResultStore().list_for_run(**scope)
    entry = next(item for item in catalog if item["result_id"] == saved["result_id"])
    ctx = SimpleNamespace(user_id=scope["user_id"], tenant_id=scope["tenant_id"])

    pages, limitations = await Synthesizer._prepare_result_evidence(
        references=[{"result_id": saved["result_id"], "operation": "netbox_get_objects", "revision": 1}],
        catalog_by_id={saved["result_id"]: entry}, ctx=ctx, run_id=scope["run_id"],
    )
    assert [item["code"] for item in limitations] == ["selected_result_page_partial"]
    assert len(pages) == 1
    assert pages[0]["result_id"] == saved["result_id"] and pages[0]["revision"] == 1
    assert pages[0]["records"] == [{"id": index, "name": f"row-{index}"} for index in range(5)]
    assert pages[0]["read_complete"] is False and pages[0]["next_offset"] == 5
    assert pages[0]["source_complete"] == entry["source_complete"]
    assert pages[0]["source_total"] == entry["source_total"]

    stale_pages, stale_limitations = await Synthesizer._prepare_result_evidence(
        references=[{"result_id": saved["result_id"], "operation": "netbox_get_objects", "revision": 2}],
        catalog_by_id={saved["result_id"]: entry}, ctx=ctx, run_id=scope["run_id"],
    )
    assert stale_pages == []
    assert stale_limitations[0]["code"] == "selected_result_revision_changed"

    denied, denied_limitations = await Synthesizer._prepare_result_evidence(
        references=[{"result_id": saved["result_id"], "operation": "netbox_get_objects"}],
        catalog_by_id={saved["result_id"]: entry},
        ctx=SimpleNamespace(user_id=uuid4(), tenant_id=uuid4()), run_id=scope["run_id"],
    )
    assert denied == []
    assert denied_limitations[0]["code"] == "selected_result_read_unavailable"

    oversized, _ = await workspace.save_source(payload={"count": 1, "results": [{"text": "x" * 20_000}], "next": None},
        source_tool="external.large", arguments={}, operation="external.large", call_id="oversized",
        task_id="task", agent_execution_id="agent", **scope)
    oversized_catalog = await ToolResultStore().list_for_run(**scope)
    oversized_entry = next(item for item in oversized_catalog if item["result_id"] == oversized["result_id"])
    oversized_pages, oversized_limitations = await Synthesizer._prepare_result_evidence(
        references=[{"result_id": oversized["result_id"], "operation": "external.large"}],
        catalog_by_id={oversized["result_id"]: oversized_entry}, ctx=ctx, run_id=scope["run_id"],
    )
    assert oversized_pages[0]["record_too_large"] is True and oversized_pages[0]["records"] == []
    assert any(item["code"] == "selected_result_page_partial" for item in oversized_limitations)


@pytest.mark.asyncio
async def test_inventory_prompt_sql_counts_devices_instead_of_unique_models(workspace_pg):
    from app.services.inventory_sql_prompt import DEVICE_MODEL_COUNTS_SQL

    workspace, scope, _ = workspace_pg
    items = [
        {"id": 1, "device_type": {"model": "A"}},
        {"id": 2, "device_type": {"model": "A"}},
        {"id": 3, "device_type": {"model": "A"}},
        {"id": 4, "device_type": {"model": "B"}},
        {"id": 5, "device_type": None},
        {"id": 6, "device_type": {"model": ""}},
    ]
    saved, _ = await save(workspace, scope, items=items, total=6, next_page=False)
    result = await ToolResultStore().execute_sql(
        sql=DEVICE_MODEL_COUNTS_SQL.format(sql_ref=saved["sql_ref"]),
        call_id="model-counts", task_id="task", agent_execution_id="agent", **scope,
    )
    assert result["rows"] == [
        {"device_type": "A", "device_count": 3},
        {"device_type": "Тип не указан", "device_count": 2},
        {"device_type": "B", "device_count": 1},
    ]
    assert sum(row["device_count"] for row in result["rows"]) == saved["row_count"] == 6
    assert result["row_count"] == 3  # groups, not devices
    assert result["source_complete"] is True


@pytest.mark.asyncio
async def test_zero_and_50000_items_are_stored_uniformly(workspace_pg):
    workspace, scope, engine = workspace_pg
    empty, _ = await save(workspace, scope, items=[], total=0, next_page=False)
    read = await workspace.read(result_id=empty["result_id"], **scope)
    assert read["value"] == [] and read["read_complete"] and read["source_complete"]
    large, _ = await save(workspace, scope, call="large", items=[{"id": i} for i in range(50000)], total=50000, next_page=False)
    assert large["row_count"] == 50000 and not large["inline_complete"]
    read = await workspace.read(result_id=large["result_id"], offset=49999, **scope)
    assert read["value"] == [{"id": 49999}] and read["read_complete"]
    query = await ToolResultStore().execute_sql(sql=f"SELECT count(*) AS count FROM {large['sql_ref']}",
        call_id="count", task_id="task", agent_execution_id="agent", **scope)
    assert query["rows"] == [{"count": 50000}]


@pytest.mark.asyncio
async def test_native_load_rechecks_permissions_and_keeps_same_dataset(workspace_pg):
    from unittest.mock import AsyncMock
    from app.agents.context import ToolCall, ToolContext, ToolResult
    from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
    from app.agents.runtime.tools import OperationExecutionFacade
    from app.agents.runtime.result_workspace_tools import with_workspace_operations
    workspace, scope, _ = workspace_pg
    saved, _ = await save(workspace, scope)
    source = ResolvedOperation(operation_slug="netbox_get_objects", operation="read", name="Devices",
        source="mcp", scope="system", data_instance_id="netbox", data_instance_slug="netbox",
        input_schema={"type": "object"}, target=ProviderExecutionTarget(operation_slug="netbox_get_objects",
            provider_type="mcp", mcp_tool_name="netbox_get_objects", data_instance_id="netbox", data_instance_slug="netbox"))
    operations = with_workspace_operations([source])
    ctx = ToolContext(tenant_id=scope["tenant_id"], user_id=scope["user_id"], extra={"runtime_root_run_id": scope["run_id"]})
    executor = type("Executor", (), {"execute": AsyncMock(return_value=ToolResult.ok({"count": 3,
        "results": [{"id": 2}, {"id": 3}], "next": None}))})()
    deps = ctx.get_runtime_deps()
    deps.operation_executor = executor
    ctx.set_runtime_deps(deps)
    facade = OperationExecutionFacade()
    denied, _ = await facade.execute(ToolCall(id="denied", tool_name="result.load", arguments={"result_id": saved["result_id"]}),
        ctx, [operation for operation in operations if operation.operation_slug != "netbox_get_objects"])
    assert denied.success and "unavailable" in denied.data["load_error"]
    executor.execute.assert_not_awaited()
    loaded, _ = await facade.execute(ToolCall(id="load", tool_name="result.load", arguments={"result_id": saved["result_id"], "mode": "remaining"}), ctx, operations)
    assert loaded.success and loaded.data["result_id"] == saved["result_id"]
    assert loaded.data["row_count"] == 3 and loaded.data["revision"] == 2
    assert loaded.data["source_complete"] and not loaded.data["budget_reached"]
    assert executor.execute.await_args.args[0].arguments["offset"] == 1
    denied_read, _ = await facade.execute(ToolCall(id="read-denied", tool_name="result.read", arguments={"result_id": saved["result_id"]}),
        ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={"runtime_root_run_id": scope["run_id"]}), operations)
    assert not denied_read.success


@pytest.mark.asyncio
async def test_sql_join_and_oversized_read_preserve_data(workspace_pg):
    workspace, scope, _ = workspace_pg
    first, _ = await save(workspace, scope, call="left", items=[{"id": 1, "name": "x" * 10000}], total=1, next_page=False)
    other = await ToolResultStore().save(payload=[{"device": 1, "ticket": "OPS-1"}], operation="jira",
        call_id="right", task_id="task", agent_execution_id="agent", **scope)
    read = await workspace.read(result_id=first["result_id"], **scope)
    assert read["record_too_large"] and not read["read_complete"] and read["value"] == []
    read = await workspace.read(result_id=first["result_id"], fields=["id"], **scope)
    assert read["value"] == [{"id": 1}] and read["read_complete"]
    result = await ToolResultStore().execute_sql(sql=f"SELECT d.id, j.ticket FROM {first['sql_ref']} d JOIN {other['sql_ref']} j ON j.device = d.id",
        call_id="join", task_id="task", agent_execution_id="agent", **scope)
    assert result["rows"] == [{"id": 1, "ticket": "OPS-1"}]
    assert len(result["source_result_ids"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("json_columns", [False, True])
async def test_native_sql_saves_uuid_execution_and_json_columns(workspace_pg, json_columns):
    from app.agents.context import ToolCall, ToolContext
    from app.agents.runtime.result_workspace_tools import execute_workspace
    workspace, scope, engine = workspace_pg
    records = [{"name": None, "device_type": {"display": "Router"}, "status": {"label": "Active"}},
               {"name": "r1", "device_type": {"display": "Switch"}, "status": {"label": "Offline"}}]
    saved, _ = await save(workspace, scope, items=records, total=2, next_page=False)
    execution_id = uuid4()
    ctx = ToolContext(tenant_id=scope["tenant_id"], user_id=scope["user_id"],
                      extra={"runtime_root_run_id": scope["run_id"], "run_id": execution_id, "runtime_task_id": "task"})
    type_expression = "device_type->>'display'"
    result = await execute_workspace(ToolCall(id="native-query", tool_name="result.sql", arguments={
        "sql": f"SELECT name, {type_expression} AS type, status->>'label' AS status FROM {saved['sql_ref']} ORDER BY name NULLS FIRST"
    }), ctx, None, [], 30)
    assert result.success, result.error
    assert result.data["rows"] == [{"name": None, "type": "Router", "status": "Active"},
                                  {"name": "r1", "type": "Switch", "status": "Offline"}]
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT agent_execution_id FROM runtime_tool_payloads WHERE call_id='native-query'"))).scalar_one() == str(execution_id)
    read = await workspace.read(result_id=result.data["result_id"], **scope)
    assert read["value"] == result.data["rows"]


@pytest.mark.asyncio
async def test_schema_pages_and_read_use_the_same_column_names(workspace_pg):
    workspace, scope, _ = workspace_pg
    row = {"name": "r1", "device_type": {"display": "Router"}, "status": {"label": "Active"},
           **{f"field_{i}": i for i in range(40)}}
    saved, _ = await save(workspace, scope, items=[row], total=1, next_page=False)
    ref = {**scope, "result_id": saved["result_id"]}
    columns, offset = {}, 0
    while True:
        description = await workspace.describe(offset=offset, limit=5, **ref)
        assert len(description["sql_columns"]) <= 5
        from app.agents.context import ToolResult
        from app.agents.runtime.tools import OperationExecutionFacade
        import json
        visible = json.loads(OperationExecutionFacade.format_result_for_context(ToolResult.ok(description, workspace_view=True)))
        assert visible["sql_columns"] == description["sql_columns"]
        columns.update(description["sql_columns"])
        offset = description["next_schema_offset"]
        if offset is None:
            break
    assert description["schema_total_columns"] == len(columns)
    assert "device_type" in columns and "device_type_display" not in columns
    page = await workspace.read(fields=["name", "device_type", "status"], **ref)
    assert page["value"] == [{"name": "r1", "device_type": {"display": "Router"}, "status": {"label": "Active"}}]
    with pytest.raises(ToolResultStoreError, match="Unknown.*field"):
        await workspace.read(fields=["device_type.display"], **ref)
    with pytest.raises(ToolResultStoreError, match="Unknown.*field"):
        await workspace.read(fields=["invented_field"], **ref)
    filtered = await workspace.describe(query="device_type", **ref)
    assert set(filtered["sql_columns"]) == {"device_type"}
    query = await ToolResultStore().execute_sql(sql=f"SELECT * FROM {saved['sql_ref']}",
        call_id="all-columns", task_id="task", agent_execution_id="agent", **scope)
    assert set(query["rows"][0]) == set(columns)
    assert query["rows"][0] == row


@pytest.mark.asyncio
async def test_initial_records_and_original_page_commit_atomically(workspace_pg):
    workspace, scope, engine = workspace_pg
    with pytest.raises(ToolResultStoreError, match="persist"):
        await ToolResultStore().save(payload=[{"id": 1}], operation="netbox_get_objects", call_id="broken-page",
            task_id="task", agent_execution_id="agent", source_page={"page_key": "x" * 65,
            "payload": {"results": [{"id": 1}]}, "meta": {}}, **scope)
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM runtime_tool_payloads WHERE call_id='broken-page'"))).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM runtime_tool_result_rows"))).scalar_one() == 0
    saved, _ = await save(workspace, scope, items=[{"id": 1, "ip": None}], total=1, next_page=False)
    async with engine.connect() as conn:
        page = (await conn.execute(text("SELECT payload FROM runtime_tool_result_pages WHERE result_id=CAST(:id AS uuid)"),
                                   {"id": saved["result_id"]})).scalar_one()
        assert page["results"] == [{"id": 1, "ip": None}]


@pytest.mark.asyncio
async def test_single_record_meta_identity_and_standard_queries(workspace_pg):
    workspace, scope, engine = workspace_pg
    row = {"id": 1, "name": "router", "status": {"value": "active"}, "optional": None}
    saved, _ = await save(workspace, scope, items=[row], total=3)
    ref = {**scope, "result_id": saved["result_id"]}
    state = await workspace.state(**ref)
    assert state["call_id"] == "first"
    assert set(state["dataset_meta"]["table_schema"]) == set(row)
    assert state["dataset_meta"]["table_schema"]["status"]["type"] == "jsonb"
    read = await workspace.read(**ref)
    assert read["value"] == [row]
    params = dict(call_id="group", task_id="task", agent_execution_id="agent")
    grouped = await workspace.standard_query(kind="aggregate", columns=["status"], **params, **ref)
    assert grouped["rows"] == [{"status": {"value": "active"}, "count": 1}]
    assert not grouped["source_complete"]
    found = await workspace.standard_query(kind="find", q="ACTIVE", columns=["name"],
        **{**params, "call_id": "find"}, **ref)
    assert found["rows"] == [{"name": "router"}]
    hostile = await workspace.standard_query(kind="find", q="%' OR true --", **{**params, "call_id": "hostile"}, **ref)
    assert hostile["rows"] == []
    args = state["dataset_meta"]["next_arguments"]
    await workspace.append_page(payload={"count": 3, "next": None, "results": [
        {"id": 2, "name": "switch", "new_field": True}, {"id": 3, "name": "other"}]},
        source_tool="netbox_get_objects", arguments=args, expected_revision=1, call_id="page", **ref)
    updated = await workspace.state(**ref)
    assert updated["row_count"] == 3 and updated["source_complete"]
    assert updated["dataset_meta"]["table_schema"]["new_field"]["type"] == "boolean"
    async with engine.connect() as conn:
        values = (await conn.execute(text("SELECT id, result_id FROM runtime_tool_result_rows WHERE result_id=CAST(:id AS uuid)"),
                                    {"id": saved["result_id"]})).all()
    assert len({value.id for value in values}) == 3
    repeated, _ = await save(workspace, scope, items=[row], total=1, next_page=False)
    assert repeated["result_id"] == saved["result_id"] and repeated["revision"] == 2
    assert (await workspace.state(**ref))["row_count"] == 3


@pytest.mark.asyncio
async def test_sql_rejects_physical_tables_and_foreign_results(workspace_pg):
    workspace, scope, _ = workspace_pg
    saved, _ = await save(workspace, scope)
    for sql in ["SELECT * FROM runtime_tool_result_rows", "SELECT * FROM public.runtime_tool_payloads",
                "SELECT pg_read_file('/etc/passwd')", f"SELECT * FROM {saved['sql_ref']}; SELECT 1"]:
        with pytest.raises(ToolResultStoreError):
            await ToolResultStore().execute_sql(sql=sql, call_id="denied", task_id=None, agent_execution_id=None, **scope)
    with pytest.raises(ToolResultStoreError):
        await ToolResultStore().execute_sql(sql=f"SELECT * FROM {saved['sql_ref']}", call_id="foreign",
            task_id=None, agent_execution_id=None, **{**scope, "user_id": uuid4()})


@pytest.mark.asyncio
@pytest.mark.parametrize("source_tool", ["netbox_get_objects", "netbox_search_objects"])
async def test_mock_mcp_to_records_schema_model_message_and_sql(workspace_pg, source_tool):
    import json
    from app.agents.context import ToolResult
    from app.agents.operation_executor import DirectOperationExecutor
    from app.agents.runtime.tools import OperationExecutionFacade

    workspace, scope, _ = workspace_pg
    rows = [{"id": 1, "name": "r1", "status": {"value": "active", "label": "Active"},
             "device_type": {"model": "Router", "manufacturer": {"name": "Vendor"}},
             "tags": [{"name": "edge"}], "ip": None, "enabled": False, "count": 0, "a.b": "literal"},
            {"id": 2, "name": "r2", "status": {"value": "offline"}, "optional": "second row"}]
    page = {"results": rows, "count": 2, "next": None}
    args = {"object_type": "dcim.device"}
    if source_tool == "netbox_search_objects":
        page = {"results": [{"object_type": "dcim.device", **page}], "errors": [], "searched_types": ["dcim.device"]}
        args = {"q": "r", "object_types": ["dcim.device"]}
    # Slim text must never replace the original MCP structuredContent.
    mcp = {"content": [{"type": "text", "text": "slim preview"}], "structuredContent": page}
    tool = DirectOperationExecutor._tool_result_from_payload(mcp)
    saved, normalized = await workspace.save_source(payload=tool.data, source_tool=source_tool,
        arguments=args, operation=source_tool, call_id="mock", task_id="task", agent_execution_id="agent", **scope)
    ref = {**scope, "result_id": saved["result_id"]}
    expected = set().union(*(row.keys() for row in rows))
    state = await workspace.state(**ref)
    assert state["row_count"] == 2 and state["source_complete"]
    assert set(state["observed_schema"]) == expected
    assert set(state["dataset_meta"]["table_schema"]) == expected
    assert state["dataset_meta"]["table_schema"]["device_type"]["type"] == "jsonb"
    described = await workspace.describe(limit=100, **ref)
    assert set(described["sql_columns"]) == expected and described["schema_page_complete"]
    read = await workspace.read(**ref)
    assert read["value"] == rows
    view = json.loads(OperationExecutionFacade.format_result_for_context(ToolResult.ok(normalized), stored_result=saved))
    assert view["records"] == rows
    assert "next_action" not in view
    assert view["result_id"] == saved["result_id"]
    query_args = dict(call_id="sql", task_id="task", agent_execution_id="agent", **scope)
    result = await ToolResultStore().execute_sql(sql=f'''SELECT name, status->>'value' AS status,
        device_type->'manufacturer'->>'name' AS vendor, tags->0->>'name' AS tag,
        ip, enabled, count, "a.b", optional FROM {saved["sql_ref"]} ORDER BY id''', **query_args)
    assert result["rows"][0] == {"name": "r1", "status": "active", "vendor": "Vendor", "tag": "edge",
                                 "ip": None, "enabled": False, "count": 0, "a.b": "literal", "optional": None}
    assert result["rows"][1]["optional"] == "second row"
    full = await ToolResultStore().execute_sql(sql=f'SELECT * FROM {saved["sql_ref"]} ORDER BY id',
        **{**query_args, "call_id": "all-fields"})
    assert set(full["rows"][0]) == expected and full["rows"][0]["device_type"] == rows[0]["device_type"]
    grouped = await workspace.standard_query(kind="aggregate", columns=["status"], call_id="groups",
        task_id="task", agent_execution_id="agent", **ref)
    assert sum(row["count"] for row in grouped["rows"]) == 2


@pytest.mark.asyncio
async def test_search_append_retains_missing_type_coverage(workspace_pg):
    workspace, scope, _ = workspace_pg
    args = {"q": "r", "object_types": ["dcim.device", "dcim.site"], "limit": 1}
    payload = {"results": [{"object_type": "dcim.device", "results": [{"name": "r1"}], "count": 2,
                           "next": "https://netbox/?offset=1&limit=1"}],
               "errors": [{"object_type": "dcim.site", "status": 403}], "searched_types": args["object_types"]}
    saved, _ = await workspace.save_source(payload=payload, source_tool="netbox_search_objects", arguments=args,
        operation="netbox_search_objects", call_id="partial", task_id="task", agent_execution_id="agent", **scope)
    ref = {**scope, "result_id": saved["result_id"]}
    state = await workspace.state(**ref)
    next_args = state["dataset_meta"]["next_arguments"]
    final = {"results": [{"object_type": "dcim.device", "results": [{"name": "r2"}], "count": 2, "next": None},
                         {"object_type": "dcim.site", "results": [], "count": 0, "next": None}],
             "errors": [], "searched_types": args["object_types"]}
    await workspace.append_page(payload=final, source_tool="netbox_search_objects", arguments=next_args,
        expected_revision=1, call_id="continuation", **ref)
    state = await workspace.state(**ref)
    assert state["row_count"] == 2 and not state["source_complete"]
    assert state["dataset_meta"]["coverage_incomplete"]
    assert state["dataset_meta"]["has_next"] is False


@pytest.mark.asyncio
async def test_decimal_page_append_and_replay_are_exact_and_idempotent(workspace_pg):
    workspace, scope, _ = workspace_pg
    args = {"object_type": "dcim.device", "limit": 1}
    first = {"count": 2, "results": [{"id": 1, "weight": 1.25}],
             "next": "https://netbox/api/?offset=1&limit=1"}
    saved, _ = await workspace.save_source(payload=first, source_tool="netbox_get_objects",
        arguments=args, operation="netbox_get_objects", call_id="decimal-source",
        task_id="task", agent_execution_id="agent", **scope)
    state = await workspace.state(result_id=saved["result_id"], **scope)
    appended = await workspace.append_page(payload={"count": 2,
        "results": [{"id": 2, "weight": 2.5}], "next": None},
        source_tool="netbox_get_objects", arguments=state["dataset_meta"]["next_arguments"],
        expected_revision=1, call_id="decimal-page", result_id=saved["result_id"], **scope)
    assert appended == {"appended": True, "revision": 2}
    repeated, _ = await workspace.save_source(payload=first, source_tool="netbox_get_objects",
        arguments=args, operation="netbox_get_objects", call_id="decimal-source",
        task_id="task", agent_execution_id="agent", **scope)
    state = await workspace.state(result_id=saved["result_id"], **scope)
    assert repeated["revision"] == 2 and state["row_count"] == 2
    assert (await workspace.read(result_id=saved["result_id"], **scope))["value"] == [
        {"id": 1, "weight": Decimal("1.25")}, {"id": 2, "weight": Decimal("2.5")}]


@pytest.mark.asyncio
async def test_jira_nested_incompleteness_survives_final_issue_page(workspace_pg):
    workspace, scope, _ = workspace_pg
    args = {"jql": "project = NET"}
    first = {"startAt": 0, "total": 2, "issues": [{"key": "NET-1",
        "fields": {"comment": {"total": 10, "comments": [{"body": "first"}]}}}]}
    saved, _ = await workspace.save_source(payload=first, source_tool="jira_search_issues",
        arguments=args, operation="jira_search_issues", call_id="jira-source",
        task_id="task", agent_execution_id="agent", **scope)
    state = await workspace.state(result_id=saved["result_id"], **scope)
    await workspace.append_page(payload={"startAt": 1, "total": 2, "issues": [{"key": "NET-2",
        "fields": {"comment": {"total": 1, "comments": [{"body": "complete"}]}}}]},
        source_tool="jira_search_issues", arguments=state["dataset_meta"]["next_arguments"],
        expected_revision=1, call_id="jira-page", result_id=saved["result_id"], **scope)
    state = await workspace.state(result_id=saved["result_id"], **scope)
    assert state["dataset_meta"]["coverage_incomplete"] is True
    assert state["source_complete"] is False


@pytest.mark.asyncio
async def test_find_escapes_and_mixed_root_rows_preserve_source_values(workspace_pg):
    workspace, scope, _ = workspace_pg
    saved = await ToolResultStore().save(payload=[{"path": r"C:\\temp\\report.txt",
        "quoted": 'say "hello"', "multiline": "first\nsecond"}],
        call_id="find-escaped", operation="review.source", task_id="task",
        agent_execution_id="agent", **scope)
    for index, query in enumerate((r"C:\\temp\\report.txt", 'say "hello"', "first\nsecond")):
        result = await workspace.standard_query(kind="find", q=query,
            result_id=saved["result_id"], call_id=f"find-{index}", task_id="task",
            agent_execution_id="agent", **scope)
        assert result["row_count"] == 1

    mixed = await ToolResultStore().save(payload=[1, {"name": "object"}],
        call_id="mixed-root", operation="review.source", task_id="task",
        agent_execution_id="agent", **scope)
    queried = await ToolResultStore().execute_sql(
        sql=f'SELECT value, name FROM {mixed["sql_ref"]} ORDER BY name NULLS FIRST',
        call_id="mixed-root-query", task_id="task", agent_execution_id="agent", **scope)
    assert queried["rows"] == [{"value": Decimal("1"), "name": None},
                                {"value": {"name": "object"}, "name": "object"}]
