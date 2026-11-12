"""Real PostgreSQL checks for result protocol persistence boundaries."""
from __future__ import annotations

import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.services.result_workspace import ResultWorkspace
from app.services.tool_result_store import ToolResultStore

pytestmark = pytest.mark.skipif(os.getenv("TOOL_WORKSPACE_PG") != "1", reason="requires isolated tool-results PostgreSQL")


@pytest_asyncio.fixture
async def isolated_results():
    schema = "test_handoff_" + uuid4().hex
    url = get_settings().TOOL_RESULTS_DB_URL
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}},
        json_deserializer=lambda value: json.loads(value, parse_float=Decimal))

    def migrate(connection, through: int = 5, start: int = 1):
        with Operations.context(MigrationContext.configure(connection)):
            for number in range(start, through + 1):
                filename = f"{number:04d}_" + {
                    1: "tool_payloads.py", 2: "sql_result_rows.py", 3: "result_datasets.py",
                    4: "virtual_table_rows.py", 5: "nullable_source_complete.py",
                }[number]
                path = Path("app/tool_results_migrations/versions") / filename
                spec = importlib.util.spec_from_file_location(filename[:-3], path)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: migrate(sync, through=4))
    from app.services import result_workspace, tool_result_store
    old_workspace_engine = result_workspace.get_tool_results_engine
    old_store_engine = tool_result_store.get_tool_results_engine
    result_workspace.get_tool_results_engine = lambda: engine
    tool_result_store.get_tool_results_engine = lambda: engine
    yield ResultWorkspace(), {"run_id": "run-" + uuid4().hex, "tenant_id": uuid4(), "user_id": uuid4()}, engine, migrate
    result_workspace.get_tool_results_engine = old_workspace_engine
    tool_result_store.get_tool_results_engine = old_store_engine
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


@pytest.mark.asyncio
async def test_nullable_migration_append_coverage_and_nested_reader(isolated_results):
    workspace, scope, engine, migrate = isolated_results
    store = ToolResultStore()
    legacy = await store.save(run_id=scope["run_id"], call_id="legacy", operation="legacy",
        tenant_id=scope["tenant_id"], user_id=scope["user_id"], task_id=None,
        agent_execution_id=None, payload=[{"x": 1}], dataset_meta={}, source_complete=True)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE runtime_tool_payloads SET source_complete=TRUE, dataset_meta='{}'::jsonb WHERE id=CAST(:id AS uuid)"),
                                 {"id": legacy["result_id"]})
        await connection.run_sync(lambda sync: migrate(sync, through=5, start=5))
        result = await connection.execute(text("SELECT source_complete FROM runtime_tool_payloads WHERE id=CAST(:id AS uuid)"),
                                          {"id": legacy["result_id"]})
        assert result.scalar_one() is None

    first, _ = await workspace.save_source(payload={"rows": [{"nested": {"text": "abcdefghijk", "second": 1, "third": 2}}],
        "total": 2, "has_more": True}, source_tool="collection.search", arguments={"offset": 0, "limit": 1},
        operation="collection.search", call_id="page-0", task_id="task", agent_execution_id="agent", **scope)
    state = await workspace.state(result_id=first["result_id"], **scope)
    assert state["source_complete"] is False
    assert state["dataset_meta"].get("coverage_incomplete") is None
    query_page = await workspace.standard_query(kind="find", q="text", offset=0, limit=1,
        result_id=first["result_id"], revision=1, call_id="find-page", task_id="task",
        agent_execution_id="agent", **scope)
    assert query_page["input_result_id"] == first["result_id"]
    assert query_page["input_revision"] == 1
    assert query_page["page_may_have_more"] is True
    assert query_page["query_complete"] is True
    continuation = state["dataset_meta"]["next_arguments"]
    assert continuation == {"offset": 1, "limit": 1}
    await workspace.append_page(payload={"rows": [{"nested": {"text": "last"}}],
        "total": 2, "has_more": False}, source_tool="collection.search", arguments=continuation,
        expected_revision=1, call_id="page-1", result_id=first["result_id"], **scope)
    state = await workspace.state(result_id=first["result_id"], **scope)
    assert state["source_complete"] is True

    pointer_read = await workspace.read(result_id=first["result_id"], path="/nested/text",
        text_offset=2, text_limit=3, limit=1, **scope)
    assert pointer_read["value"] == ["cde"]
    assert pointer_read["next_text_offset"] == 5
    from app.agents.context import ToolResult
    from app.agents.runtime.tools import OperationExecutionFacade
    import json as json_module
    text_view = json_module.loads(OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(pointer_read, workspace_view=True), operation_slug="result.read"))
    assert text_view["read_complete"] is False
    next_text_args = text_view["next_action"]["arguments"]
    assert next_text_args["text_offset"] == 5 and next_text_args["path"] == "/nested/text"
    next_text = await workspace.read(**next_text_args, **scope)
    assert next_text["value"] == ["fgh"]

    child_read = await workspace.read(result_id=first["result_id"], path="/nested",
        child_offset=0, child_limit=1, limit=1, **scope)
    child_view = json_module.loads(OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(child_read, workspace_view=True), operation_slug="result.read"))
    assert child_view["read_complete"] is False
    next_child_args = child_view["next_action"]["arguments"]
    assert next_child_args["child_offset"] == 1
    next_child = await workspace.read(**next_child_args, **scope)
    assert next_child["value"][0]["children"][0]["key"] == "text"


@pytest.mark.asyncio
async def test_continuation_token_is_internal_and_model_rows_are_redacted(isolated_results):
    workspace, scope, _, _ = isolated_results
    payload = {"issues": [{"id": "1", "summary": "safe", "api_token": "row-secret"}],
        "total": 2, "nextPageToken": "cursor-secret"}
    saved, visible = await workspace.save_source(payload=payload, source_tool="jira_search",
        arguments={"jql": "project = X"}, operation="jira_search", call_id="jira-first",
        task_id="task", agent_execution_id="agent", **scope)
    assert "cursor-secret" not in json.dumps(visible)
    assert visible["value"][0]["api_token"] == "***"
    state = await workspace.state(result_id=saved["result_id"], **scope)
    assert state["dataset_meta"]["next_arguments"]["page_token"] == "cursor-secret"
    assert "row-secret" not in json.dumps(state["sample"])

    same, _ = await workspace.save_source(payload=payload, source_tool="jira_search",
        arguments={"jql": "project = X"}, operation="jira_search", call_id="jira-first",
        task_id="task", agent_execution_id="agent", **scope)
    assert same["result_id"] == saved["result_id"]
    assert same["revision"] == saved["revision"]
