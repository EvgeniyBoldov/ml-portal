from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.capability_resolver import CapabilityCandidate
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.operation_router import OperationRouter, OperationResolveResult
from app.agents.runtime_graph_builder import RuntimeExecutionGraphBuilder


@pytest.mark.asyncio
async def test_resolve_system_tools_creates_global_binding_without_collection_context():
    router = OperationRouter.__new__(OperationRouter)
    router.system_capability_resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=[
                CapabilityCandidate(
                    canonical_op_slug="file.read",
                    raw_tool_slug="file.read",
                    scope_kind="system",
                    discovered_tool=SimpleNamespace(slug="file.read", domains=["system"], source="local"),
                )
            ]
        )
    )
    router.operation_resolver = SimpleNamespace(
        _resolve_execution_credentials=AsyncMock(return_value=None)
    )

    operation = ResolvedOperation(
        operation_slug="file.read",
        operation="file.read",
        name="Read File",
        scope="system",
        description="Read file",
        input_schema={},
        data_instance_id="system",
        data_instance_slug="system",
        provider_instance_id="system",
        provider_instance_slug="system",
        source="local",
        target=ProviderExecutionTarget(
            operation_slug="file.read",
            provider_type="local",
            provider_instance_id="system",
            provider_instance_slug="system",
            data_instance_id="system",
            data_instance_slug="system",
            handler_slug="file.read",
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

    assert [item.operation_slug for item in result.resolved_operations] == ["file.read"]
    binding = graph_builder.build().get("file.read")
    assert binding is not None
    assert binding.context.scope == "system"
    assert binding.context.collection_slug is None
    assert binding.context.allowed_collection_slugs == []
    assert binding.target.data_instance_slug == "system"


@pytest.mark.asyncio
async def test_resolve_system_tools_noops_when_none_available():
    router = OperationRouter.__new__(OperationRouter)
    router.system_capability_resolver = SimpleNamespace(resolve=AsyncMock(return_value=[]))
    router.operation_resolver = SimpleNamespace(
        _resolve_execution_credentials=AsyncMock(return_value=None)
    )
    router.operation_builder = SimpleNamespace(_build_single_operation=AsyncMock())

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

    assert result.resolved_operations == []
    assert graph_builder.build().bindings == {}
