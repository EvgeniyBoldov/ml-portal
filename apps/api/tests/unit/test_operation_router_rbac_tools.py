from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.data_instance_resolver import RuntimeDataInstanceResolver
from app.agents.operation_executor import _parse_mcp_response_body
from app.agents.operation_router import OperationRouter
from app.models.tool_instance import ToolInstance
from app.services.permission_service import EffectivePermissions


def _instance(**overrides) -> ToolInstance:
    base = dict(
        id=uuid4(),
        slug="collection-tickets",
        name="Collection Tickets",
        description="Tickets",
        instance_kind="data",
        placement="local",
        domain="collection.table",
        url="",
        config={},
        is_active=True,
    )
    base.update(overrides)
    return ToolInstance(**base)


def _provider(**overrides) -> ToolInstance:
    base = dict(
        id=uuid4(),
        slug="local-provider",
        name="Local Provider",
        description="Local",
        instance_kind="service",
        placement="local",
        domain="collection.table",
        url="",
        config={},
        is_active=True,
    )
    base.update(overrides)
    return ToolInstance(**base)


@pytest.mark.asyncio
async def test_operation_router_passes_effective_permissions_to_operation_resolver():
    router = OperationRouter(session=MagicMock())
    effective_permissions = EffectivePermissions(
        tool_permissions={"collection.search": False},
        default_tool_allow=True,
        default_collection_allow=True,
    )
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(
        return_value=effective_permissions
    )

    ready_instance = _instance()
    router.data_instance_resolver.resolve = AsyncMock(
        return_value=[
            SimpleNamespace(
                instance=ready_instance,
                collection=None,
                provider=None,
                readiness_reason="ready",
                runtime_domain="collection.table",
            )
        ]
    )
    router.operation_resolver.resolve_for_instance = AsyncMock(return_value=[])

    result = await router.resolve(user_id=uuid4(), tenant_id=uuid4())

    assert result.resolved_operations == []
    assert result.missing.tools == [f"{ready_instance.slug} (no operations)"]
    kwargs = router.operation_resolver.resolve_for_instance.await_args.kwargs
    assert kwargs["effective_permissions"] is effective_permissions


@pytest.mark.asyncio
async def test_operation_router_reuses_effective_permissions_override():
    router = OperationRouter(session=MagicMock())
    effective_permissions = EffectivePermissions(
        tool_permissions={"collection.search": True},
        default_tool_allow=False,
        default_collection_allow=False,
    )
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(
        side_effect=AssertionError("should not be called")
    )

    ready_instance = _instance()
    router.data_instance_resolver.resolve = AsyncMock(
        return_value=[
            SimpleNamespace(
                instance=ready_instance,
                collection=None,
                provider=None,
                readiness_reason="ready",
                runtime_domain="collection.table",
            )
        ]
    )
    router.operation_resolver.resolve_for_instance = AsyncMock(return_value=[])

    result = await router.resolve(
        user_id=uuid4(),
        tenant_id=uuid4(),
        effective_permissions=effective_permissions,
    )

    assert result.effective_permissions is effective_permissions
    kwargs = router.operation_resolver.resolve_for_instance.await_args.kwargs
    assert kwargs["effective_permissions"] is effective_permissions


@pytest.mark.asyncio
async def test_operation_router_marks_collection_bound_instance_without_collection_as_missing():
    router = OperationRouter(session=MagicMock())
    effective_permissions = EffectivePermissions(
        tool_permissions={},
        default_tool_allow=True,
        default_collection_allow=True,
    )
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(
        return_value=effective_permissions
    )

    bound_instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_id": str(uuid4()),
            "collection_slug": "tickets",
        }
    )
    router.data_instance_resolver.resolve = AsyncMock(
        return_value=[
            SimpleNamespace(
                instance=bound_instance,
                collection=None,
                provider=None,
                readiness_reason="ready",
                runtime_domain="collection.table",
            )
        ]
    )
    router.operation_resolver.resolve_for_instance = AsyncMock(return_value=[])

    result = await router.resolve(user_id=uuid4(), tenant_id=uuid4())

    assert result.missing.collections == [f"{bound_instance.slug} (unresolved_collection_binding)"]
    router.operation_resolver.resolve_for_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_operation_router_marks_collection_as_missing_on_rbac_deny():
    router = OperationRouter(session=MagicMock())
    effective_permissions = EffectivePermissions(
        tool_permissions={},
        default_tool_allow=True,
        default_collection_allow=False,
    )
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(
        return_value=effective_permissions
    )

    bound_instance = _instance(
        slug="collection-tickets",
        config={
            "binding_type": "collection_asset",
            "collection_id": str(uuid4()),
            "collection_slug": "tickets",
        },
    )
    router.data_instance_resolver.resolve = AsyncMock(
        return_value=[
            SimpleNamespace(
                instance=bound_instance,
                collection=object(),
                provider=None,
                readiness_reason="ready",
                runtime_domain="collection.table",
            )
        ]
    )
    router.operation_resolver.resolve_for_instance = AsyncMock(return_value=[])

    result = await router.resolve(user_id=uuid4(), tenant_id=uuid4())

    assert result.missing.collections == ["tickets (rbac_denied)"]
    router.operation_resolver.resolve_for_instance.assert_not_awaited()


@pytest.mark.asyncio
async def test_data_instance_resolver_marks_provider_unhealthy_as_missing():
    session = MagicMock()
    instance_service = MagicMock()
    resolver = RuntimeDataInstanceResolver(
        session=session,
        instance_service=instance_service,
    )

    provider = _provider(placement="remote", url="http://mcp.example", health_status="unhealthy")
    ready_data_instance = _instance(
        placement="remote",
        domain="netbox",
        url="",
        access_via_instance_id=provider.id,
    )
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [ready_data_instance])),
            SimpleNamespace(scalar_one_or_none=lambda: provider),
        ]
    )
    instance_service.evaluate_instance_readiness = AsyncMock(
        side_effect=[(True, "ready", "linked_provider"), (True, "ready", "none")]
    )
    instances = await resolver.resolve()

    assert len(instances) == 1
    assert instances[0].provider is None
    assert instances[0].readiness_reason == "provider_unhealthy"


def test_parse_mcp_response_body_raises_on_empty_payload():
    with pytest.raises(ValueError, match="Empty MCP response body"):
        _parse_mcp_response_body("")
