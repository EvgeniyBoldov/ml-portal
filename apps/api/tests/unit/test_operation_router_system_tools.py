from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.operation_router import OperationRouter, OperationResolveResult
from app.agents.runtime_graph_builder import RuntimeExecutionGraphBuilder


@pytest.mark.asyncio
async def test_resolve_system_tools_creates_global_binding_without_collection_context():
    router = OperationRouter.__new__(OperationRouter)
    router.collection_tool_resolver = SimpleNamespace(
        _load_system_tools=AsyncMock(return_value=[SimpleNamespace(slug="collection.catalog", domains=["system"])])
    )
    router.operation_resolver = SimpleNamespace(
        _resolve_execution_credentials=AsyncMock(return_value=None)
    )

    operation = ResolvedOperation(
        operation_slug="collection.catalog_inspect",
        operation="collection.catalog_inspect",
        name="Collection Catalog Inspect",
        scope="system",
        description="Inspect any collection by slug",
        input_schema={},
        data_instance_id="system",
        data_instance_slug="system",
        provider_instance_id="system",
        provider_instance_slug="system",
        source="local",
        target=ProviderExecutionTarget(
            operation_slug="collection.catalog_inspect",
            provider_type="local",
            provider_instance_id="system",
            provider_instance_slug="system",
            data_instance_id="system",
            data_instance_slug="system",
            handler_slug="collection.catalog",
            has_credentials=True,
        ),
    )
    router.operation_builder = SimpleNamespace(
        _build_single_operation=AsyncMock(return_value=(operation, None))
    )

    result = OperationResolveResult(effective_permissions=SimpleNamespace())
    graph_builder = RuntimeExecutionGraphBuilder()

    await router._resolve_system_tools(
        result=result,
        graph_builder=graph_builder,
        seen_operation_slugs=set(),
        effective_permissions=None,
        user_id=None,
        tenant_id=None,
    )

    assert [item.operation_slug for item in result.resolved_operations] == ["collection.catalog_inspect"]
    binding = graph_builder.build().get("collection.catalog_inspect")
    assert binding is not None
    assert binding.context.scope == "system"
    assert binding.context.collection_slug is None
    assert binding.context.allowed_collection_slugs == []
    assert binding.target.data_instance_slug == "system"
