from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.contracts import (
    AvailableActions,
    MissingRequirements,
    ProviderExecutionTarget,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.execution_preflight import ExecutionPreflight
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)


def _resolved_instance(*, slug: str, collection_id: str, collection_slug: str) -> ResolvedDataInstance:
    return ResolvedDataInstance(
        instance_id=f"inst-{slug}",
        slug=slug,
        name=slug,
        domain="collection.table",
        collection_id=collection_id,
        collection_slug=collection_slug,
        placement="local",
    )


def _resolved_operation(*, instance_slug: str) -> ResolvedOperation:
    operation_slug = f"instance.{instance_slug}.search"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="local",
        data_instance_id=f"inst-{instance_slug}",
        data_instance_slug=instance_slug,
        handler_slug="collection.search",
    )
    return ResolvedOperation(
        operation_slug=operation_slug,
        operation="search",
        name=operation_slug,
        data_instance_id=f"inst-{instance_slug}",
        data_instance_slug=instance_slug,
        source="local",
        target=target,
    )


def _execution_graph(operations: list[ResolvedOperation]) -> RuntimeExecutionGraph:
    bindings = {}
    for operation in operations:
        bindings[operation.operation_slug] = OperationExecutionBinding(
            operation_slug=operation.operation_slug,
            target=operation.target,
            context=OperationRuntimeContext(
                instance_id=operation.data_instance_id,
                instance_slug=operation.data_instance_slug,
                provider_instance_id=operation.data_instance_id,
                provider_instance_slug=operation.data_instance_slug,
                has_credentials=False,
                credential_scope=operation.credential_scope,
                config={},
                provider_config={},
                domain="collection.table",
            ),
        )
    return RuntimeExecutionGraph(bindings=bindings)


def _build_preflight(
    *,
    allowed_collection_ids,
    rbac_allow_fn,
    instances: list[ResolvedDataInstance],
):
    preflight = ExecutionPreflight(session=SimpleNamespace())

    operations = [_resolved_operation(instance_slug=inst.slug) for inst in instances]
    operation_result = SimpleNamespace(
        resolved_operations=operations,
        resolved_data_instances=instances,
        execution_graph=_execution_graph(operations),
        effective_permissions=SimpleNamespace(is_collection_allowed=rbac_allow_fn),
        missing=MissingRequirements(),
    )
    preflight.operation_router = SimpleNamespace(resolve=AsyncMock(return_value=operation_result))
    preflight.agent_resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SimpleNamespace(
                agent=SimpleNamespace(slug="agent-a", allowed_collection_ids=allowed_collection_ids),
                agent_version=SimpleNamespace(compiled_prompt="prompt"),
            )
        ),
        available_actions_builder=SimpleNamespace(
            build=AsyncMock(return_value=AvailableActions()),
        ),
    )
    preflight.runtime_rbac_resolver = SimpleNamespace(
        is_agent_allowed=Mock(return_value=True),
        filter_agents_by_slug=Mock(return_value=([], [])),
    )
    preflight.trace_logger = SimpleNamespace(
        trace=SimpleNamespace(log_routing_decision=AsyncMock()),
    )
    return preflight


@pytest.mark.asyncio
async def test_collection_filter_keeps_all_when_agent_allows_any_and_rbac_allows_all():
    c1 = str(uuid4())
    c2 = str(uuid4())
    preflight = _build_preflight(
        allowed_collection_ids=None,
        rbac_allow_fn=lambda _slug: True,
        instances=[
            _resolved_instance(slug="alpha", collection_id=c1, collection_slug="collection.alpha"),
            _resolved_instance(slug="beta", collection_id=c2, collection_slug="collection.beta"),
        ],
    )

    result = await preflight.prepare(
        agent_slug="agent-a",
        user_id=uuid4(),
        tenant_id=uuid4(),
        include_routable_agents=False,
    )

    assert {inst.slug for inst in result.resolved_data_instances} == {"alpha", "beta"}
    assert {op.data_instance_slug for op in result.resolved_operations} == {"alpha", "beta"}
    assert set(result.execution_graph.bindings.keys()) == {
        "instance.alpha.search",
        "instance.beta.search",
    }


@pytest.mark.asyncio
async def test_collection_filter_applies_agent_allowed_collection_ids():
    c1 = str(uuid4())
    c2 = str(uuid4())
    preflight = _build_preflight(
        allowed_collection_ids=[c1],
        rbac_allow_fn=lambda _slug: True,
        instances=[
            _resolved_instance(slug="alpha", collection_id=c1, collection_slug="collection.alpha"),
            _resolved_instance(slug="beta", collection_id=c2, collection_slug="collection.beta"),
        ],
    )

    result = await preflight.prepare(
        agent_slug="agent-a",
        user_id=uuid4(),
        tenant_id=uuid4(),
        include_routable_agents=False,
    )

    assert [inst.slug for inst in result.resolved_data_instances] == ["alpha"]
    assert [op.data_instance_slug for op in result.resolved_operations] == ["alpha"]
    assert set(result.execution_graph.bindings.keys()) == {"instance.alpha.search"}


@pytest.mark.asyncio
async def test_collection_filter_applies_rbac_denied_slug():
    c1 = str(uuid4())
    c2 = str(uuid4())
    preflight = _build_preflight(
        allowed_collection_ids=None,
        rbac_allow_fn=lambda slug: slug != "collection.beta",
        instances=[
            _resolved_instance(slug="alpha", collection_id=c1, collection_slug="collection.alpha"),
            _resolved_instance(slug="beta", collection_id=c2, collection_slug="collection.beta"),
        ],
    )

    result = await preflight.prepare(
        agent_slug="agent-a",
        user_id=uuid4(),
        tenant_id=uuid4(),
        include_routable_agents=False,
    )

    assert [inst.slug for inst in result.resolved_data_instances] == ["alpha"]
    assert [op.data_instance_slug for op in result.resolved_operations] == ["alpha"]
    assert set(result.execution_graph.bindings.keys()) == {"instance.alpha.search"}


@pytest.mark.asyncio
async def test_collection_filter_intersects_agent_allowlist_and_rbac():
    c1 = str(uuid4())
    c2 = str(uuid4())
    preflight = _build_preflight(
        allowed_collection_ids=[c1, c2],
        rbac_allow_fn=lambda slug: slug != "collection.beta",
        instances=[
            _resolved_instance(slug="alpha", collection_id=c1, collection_slug="collection.alpha"),
            _resolved_instance(slug="beta", collection_id=c2, collection_slug="collection.beta"),
        ],
    )

    result = await preflight.prepare(
        agent_slug="agent-a",
        user_id=uuid4(),
        tenant_id=uuid4(),
        include_routable_agents=False,
    )

    assert [inst.slug for inst in result.resolved_data_instances] == ["alpha"]
    assert [op.data_instance_slug for op in result.resolved_operations] == ["alpha"]
    assert set(result.execution_graph.bindings.keys()) == {"instance.alpha.search"}
