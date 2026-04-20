from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.operation_router import OperationRouter
from app.agents.runtime.prompt_assembler import PromptAssembler
from app.models.collection import Collection
from app.models.collection import CollectionStatus
from app.models.tool_instance import ToolInstance
from app.services.permission_service import EffectivePermissions


@pytest.mark.asyncio
async def test_prompt_assembler_renders_collection_description_and_entity_type_without_semantic_layer():
    router = OperationRouter(session=MagicMock())

    effective_permissions = EffectivePermissions(
        tool_permissions={},
        default_tool_allow=True,
        default_collection_allow=True,
    )
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(return_value=effective_permissions)

    tenant_id = uuid4()
    collection = Collection(
        id=uuid4(),
        tenant_id=tenant_id,
        slug="netbox_devices",
        name="Netbox devices",
        description="Netbox devices inventory",
        entity_type="device",
        collection_type="table",
        status=CollectionStatus.READY.value,
        fields=[],
    )

    instance = ToolInstance(
        id=uuid4(),
        slug="netbox-devices-instance",
        name="Netbox devices",
        description="fallback instance description",
        instance_kind="data",
        connector_type="data",
        connector_subtype="api",
        placement="remote",
        domain="collection.api",
        url="https://netbox.example",
        config={
            "binding_type": "collection_asset",
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "collection_type": collection.collection_type,
        },
        is_active=True,
    )

    router.data_instance_resolver.resolve = AsyncMock(
        return_value=[
            SimpleNamespace(
                instance=instance,
                collection=collection,
                provider=None,
                readiness_reason="ready",
                runtime_domain="collection.api",
            )
        ]
    )

    op = ResolvedOperation(
        operation_slug="instance.netbox-devices-instance.collection.api.search",
        operation="collection.api.search",
        name="Collection API search",
        description="Search records in bound API collection",
        input_schema={"type": "object", "properties": {}},
        data_instance_id=str(instance.id),
        data_instance_slug=instance.slug,
        source="mcp",
        target=ProviderExecutionTarget(
            operation_slug="collection.api.search",
            provider_type="mcp",
            data_instance_id=str(instance.id),
            data_instance_slug=instance.slug,
        ),
    )
    router.operation_resolver.resolve_for_instance = AsyncMock(return_value=[(op, None)])

    result = await router.resolve(user_id=uuid4(), tenant_id=tenant_id)

    prompt = PromptAssembler().assemble_collection_prompt(result.resolved_data_instances)

    assert "- Description: Netbox devices inventory" in prompt
    assert "- Entity type: device" in prompt
    assert "summary" not in prompt.lower()
    assert "use_cases" not in prompt.lower()
    assert "limitations" not in prompt.lower()
    assert "policy_hints" not in prompt.lower()
