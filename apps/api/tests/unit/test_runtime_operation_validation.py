from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest

from app.agents.context import OperationCall, RuntimeDependencies, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.builtins.collection_text_search import CollectionTextSearchTool
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime import tools as runtime_tools
from app.agents.runtime.tools import OperationExecutor
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)
from app.runtime.operation_errors import RuntimeErrorCode


def _operation(*, schema: dict) -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug="collection.sql.execute",
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="sql-mcp",
        provider_url="http://sql-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="sql-demo",
        mcp_tool_name="execute_sql",
        timeout_s=20,
    )
    return ResolvedOperation(
        operation_slug="collection.sql.execute",
        operation="collection.sql.execute",
        name="SQL Execute",
        description="Execute SQL",
        input_schema=schema,
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        provider_instance_id=target.provider_instance_id,
        provider_instance_slug=target.provider_instance_slug,
        source="mcp",
        target=target,
    )


def _document_search_operation(*, schema: dict) -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug="instance.docs.collection.document.search",
        provider_type="local",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="doc-runtime",
        provider_url=None,
        data_instance_id=str(uuid4()),
        data_instance_slug="docs",
        handler_slug="collection.doc_search",
        timeout_s=20,
    )
    return ResolvedOperation(
        operation_slug="instance.docs.collection.document.search",
        operation="collection.document.search",
        name="Document Search",
        description="Search documents",
        input_schema=schema,
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        provider_instance_id=target.provider_instance_id,
        provider_instance_slug=target.provider_instance_slug,
        source="local",
        target=target,
    )


def _ctx() -> ToolContext:
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(
        operation_executor=SimpleNamespace(
            execute=AsyncMock(return_value=ToolResult.ok({"ok": True}))
        )
    )
    ctx.set_runtime_deps(deps)
    return ctx


@pytest.mark.asyncio
async def test_operation_executor_rejects_nested_type_mismatch():
    operation = _operation(
        schema={
            "type": "object",
            "required": ["filters"],
            "properties": {
                "filters": {
                    "type": "object",
                    "required": ["limit"],
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-1",
        operation_slug=operation.operation_slug,
        arguments={"filters": {"limit": "10"}},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [operation])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_INVALID_ARGS.value
    assert result.metadata.get("field_path") == "$.filters.limit"
    assert result.metadata.get("retryable") is True


@pytest.mark.asyncio
async def test_operation_executor_rejects_additional_properties_and_enum():
    operation = _operation(
        schema={
            "type": "object",
            "required": ["mode"],
            "properties": {
                "mode": {"type": "string", "enum": ["safe", "strict"]},
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-2",
        operation_slug=operation.operation_slug,
        arguments={"mode": "unsafe", "extra": 1},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [operation])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_INVALID_ARGS.value
    assert result.metadata.get("retryable") is True
    # additionalProperties validation runs before enum recursion by design
    assert result.metadata.get("field_path") == "$"


@pytest.mark.asyncio
async def test_operation_executor_marks_missing_operation_as_non_retryable():
    call = OperationCall(
        id="c-3",
        operation_slug="unknown.op",
        arguments={},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value
    assert result.metadata.get("retryable") is False


@pytest.mark.asyncio
async def test_operation_executor_builtin_validation_contract_without_jsonschema(monkeypatch):
    operation = _operation(
        schema={
            "type": "object",
            "required": ["filters"],
            "properties": {
                "filters": {
                    "type": "object",
                    "required": ["limit"],
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-fallback",
        operation_slug=operation.operation_slug,
        arguments={"filters": {"limit": "10"}},
    )
    monkeypatch.setattr(runtime_tools, "_JSONSCHEMA_AVAILABLE", False, raising=True)
    result, _ = await OperationExecutor().execute(call, _ctx(), [operation])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_INVALID_ARGS.value
    assert result.metadata.get("field_path") == "$.filters.limit"


@pytest.mark.asyncio
async def test_operation_executor_requires_exact_invoke_name():
    operation = _document_search_operation(
        schema={
            "type": "object",
            "required": ["collection_slug", "query"],
            "properties": {
                "collection_slug": {"type": "string"},
                "query": {"type": "string"},
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-alias",
        operation_slug="collection.doc_search",
        arguments={"collection_slug": "docs", "query": "nginx"},
    )
    executor_impl = AsyncMock(return_value=ToolResult.ok({"hits": [], "total": 0}))
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=SimpleNamespace(execute=executor_impl))
    ctx.set_runtime_deps(deps)

    result, _ = await OperationExecutor().execute(call, ctx, [operation])

    assert result.success is False
    assert executor_impl.await_count == 0
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_operation_executor_accepts_unique_canonical_shorthand():
    operation = _document_search_operation(
        schema={
            "type": "object",
            "required": ["collection_slug", "query"],
            "properties": {
                "collection_slug": {"type": "string"},
                "query": {"type": "string"},
            },
            "additionalProperties": False,
        }
    )
    executor_impl = AsyncMock(return_value=ToolResult.ok({"hits": [], "total": 0}))
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=SimpleNamespace(execute=executor_impl))
    ctx.set_runtime_deps(deps)
    call = OperationCall(
        id="c-short",
        operation_slug="collection.document.search",
        arguments={"query": "nginx"},
    )

    result, _ = await OperationExecutor().execute(call, ctx, [operation])

    assert result.success is True
    assert executor_impl.await_count == 1


@pytest.mark.asyncio
async def test_operation_executor_uses_prompt_schema_for_hidden_binding_fields():
    operation = _document_search_operation(
        schema={
            "type": "object",
            "required": ["collection_slug", "query"],
            "properties": {
                "collection_slug": {"type": "string"},
                "query": {"type": "string"},
            },
            "additionalProperties": False,
        }
    )
    target = operation.target
    assert target is not None
    binding = OperationExecutionBinding(
        operation_slug=operation.operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="docs",
            scope="collection",
            collection_id=str(uuid4()),
            collection_slug="docs",
            allowed_collection_slugs=["docs"],
            provider_instance_id=str(uuid4()),
            provider_instance_slug="doc-runtime",
            config={},
            provider_config={},
            domain="collection.document",
            data_instance_url=None,
            provider_url=None,
        ),
        credential=None,
    )
    executor_impl = DirectOperationExecutor()
    graph = RuntimeExecutionGraph(bindings={operation.operation_slug: binding})
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=executor_impl, execution_graph=graph)
    ctx.set_runtime_deps(deps)
    call = OperationCall(
        id="c-hidden",
        operation_slug=operation.operation_slug,
        arguments={"query": "nginx"},
    )

    result, _ = await OperationExecutor().execute(call, ctx, [operation])

    assert result.metadata.get("error_code") != RuntimeErrorCode.OPERATION_INVALID_ARGS.value


@pytest.mark.asyncio
async def test_operation_executor_strips_null_optional_args_before_validation():
    target = ProviderExecutionTarget(
        operation_slug="instance.template.collection.info",
        provider_type="local",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="template-runtime",
        data_instance_id=str(uuid4()),
        data_instance_slug="template",
        handler_slug="collection.info",
        timeout_s=20,
    )
    operation = ResolvedOperation(
        operation_slug="instance.template.collection.info",
        operation="collection.info",
        name="Collection Info",
        description="Inspect collection info",
        input_schema={
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                    },
                },
            },
            "additionalProperties": False,
        },
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        collection_slug="template",
        provider_instance_id=target.provider_instance_id,
        provider_instance_slug=target.provider_instance_slug,
        source="local",
        target=target,
    )
    executor_impl = AsyncMock(return_value=ToolResult.ok({"ok": True}))
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=SimpleNamespace(execute=executor_impl))
    ctx.set_runtime_deps(deps)
    call = OperationCall(
        id="c-null",
        operation_slug="instance.template.collection.info",
        arguments={"filters": {"status": None}},
    )

    result, _ = await OperationExecutor().execute(call, ctx, [operation])

    assert result.success is True
    executor_impl.assert_awaited_once()
    forwarded_call = executor_impl.await_args.args[0]
    assert forwarded_call.arguments == {"filters": {}}


def test_merge_local_args_injects_bound_collection_identifiers():
    target = ProviderExecutionTarget(
        operation_slug="instance.templates.collection.template.fill",
        provider_type="local",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="template-runtime",
        provider_url=None,
        data_instance_id=str(uuid4()),
        data_instance_slug="template",
        handler_slug="collection.template_fill",
    )
    collection_id = str(uuid4())
    binding = OperationExecutionBinding(
        operation_slug=target.operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="template",
            scope="collection",
            collection_id=collection_id,
            collection_slug="template",
            allowed_collection_slugs=["template"],
            provider_instance_id=str(uuid4()),
            provider_instance_slug="template-runtime",
            config={},
            provider_config={},
            domain="collection.template",
            data_instance_url=None,
            provider_url=None,
        ),
        credential=None,
    )

    merged = DirectOperationExecutor._merge_local_args(
        target,
        {"row_id": "row-1", "values": {"src_ip": "10.10.10.2"}},
        ToolContext(tenant_id=uuid4(), user_id=uuid4()),
        binding=binding,
    )

    assert merged["collection_slug"] == "template"
    assert merged["collection_id"] == collection_id


@pytest.mark.asyncio
async def test_template_search_falls_back_to_keyword_matches_when_vectors_unavailable(monkeypatch):
    async def _fake_search(self, collection, limit=50, offset=0, query=None):  # noqa: ARG001
        return [
            {
                "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                "title": "Заявка на сетевую связность",
                "description": "Шаблон заявки для сетевой связности",
                "semantic_description": "",
                "created_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
                "weight": Decimal("1.25"),
            }
        ]

    monkeypatch.setattr(
        "app.services.collection.row_service.CollectionRowService.search",
        _fake_search,
    )

    tool = CollectionTextSearchTool()
    hits = await tool._fallback_keyword_hits(  # noqa: SLF001
        session=object(),
        collection=SimpleNamespace(
            fields=[
                {"name": "title", "data_type": "string"},
                {"name": "description", "data_type": "text"},
                {"name": "semantic_description", "data_type": "text"},
                {"name": "created_at", "data_type": "datetime"},
                {"name": "weight", "data_type": "number"},
            ],
        ),
        query="заявка на сетевую связность",
        limit=5,
        vector_fields=["description"],
    )

    assert len(hits) == 1
    assert hits[0]["row_id"] == "11111111-1111-1111-1111-111111111111"
    assert hits[0]["primary_field"] == "title"
    assert hits[0]["row_data"]["created_at"] == "2026-06-30T12:00:00+00:00"
    assert hits[0]["row_data"]["weight"] == 1.25


def test_merge_local_args_rejects_mismatched_bound_collection_id():
    target = ProviderExecutionTarget(
        operation_slug="instance.templates.collection.template.fill",
        provider_type="local",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="template-runtime",
        provider_url=None,
        data_instance_id=str(uuid4()),
        data_instance_slug="template",
        handler_slug="collection.template_fill",
    )
    binding = OperationExecutionBinding(
        operation_slug=target.operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="template",
            scope="collection",
            collection_id=str(uuid4()),
            collection_slug="template",
            allowed_collection_slugs=["template"],
            provider_instance_id=str(uuid4()),
            provider_instance_slug="template-runtime",
            config={},
            provider_config={},
            domain="collection.template",
            data_instance_url=None,
            provider_url=None,
        ),
        credential=None,
    )

    with pytest.raises(ValueError, match="does not match the bound collection id"):
        DirectOperationExecutor._merge_local_args(
            target,
            {
                "collection_id": str(uuid4()),
                "row_id": "row-1",
                "values": {"src_ip": "10.10.10.2"},
            },
            ToolContext(tenant_id=uuid4(), user_id=uuid4()),
            binding=binding,
        )
