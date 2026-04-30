from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agents.data_instance_resolver import RuntimeDataInstanceResolver
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.services.tool_instance_service import ToolInstanceService


@pytest.mark.asyncio
async def test_runtime_data_instance_resolver_uses_fk_collection_binding_only():
    instance_id = uuid4()
    tenant_id = uuid4()

    instance = ToolInstance(
        id=instance_id,
        slug="netbox-devices",
        name="Netbox devices",
        description="instance description",
        instance_kind="data",
        connector_type="data",
        connector_subtype="api",
        placement="remote",
        domain="collection.api",
        url="https://netbox.example",
        config={"bindings": [{"instance_id": "legacy-ignored"}]},
        is_active=True,
    )

    collection = Collection(
        id=uuid4(),
        tenant_id=tenant_id,
        collection_type="api",
        slug="devices",
        name="Devices",
        description="Netbox devices inventory",
        entity_type="device",
        fields=[],
        status="ready",
        data_instance_id=instance_id,
        is_active=True,
    )

    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [instance])),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [collection])),
            SimpleNamespace(scalar_one_or_none=lambda: collection),
        ]
    )

    instance_service = ToolInstanceService(session)
    instance_service.evaluate_instance_readiness = AsyncMock(return_value=(True, "ready", {}))

    resolver = RuntimeDataInstanceResolver(session=session, instance_service=instance_service)
    resolved = await resolver.resolve()

    assert len(resolved) == 1
    assert resolved[0].collection is collection
    assert resolved[0].runtime_domain == "collection.api"
    assert resolved[0].readiness_reason == "ready"
