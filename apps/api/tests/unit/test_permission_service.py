from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services import permission_service as permission_service_module
from app.services.permission_service import EffectivePermissions, PermissionService


def test_effective_permissions_helpers():
    perms = EffectivePermissions(
        collection_permissions={"docs": True, "tickets": False},
        default_collection_allow=False,
    )

    assert perms.allowed_collections == ["docs"]
    assert perms.is_collection_allowed("docs") is True
    assert perms.is_collection_allowed("tickets") is False


@pytest.mark.asyncio
async def test_permission_service_maps_instance_rules_to_collection_permissions(monkeypatch):
    service = PermissionService(session=AsyncMock())
    tenant_id = UUID("22222222-2222-2222-2222-222222222222")
    collection_id = UUID("11111111-1111-1111-1111-111111111111")
    service.rule_repo.list_platform_rules = AsyncMock(return_value=[])
    service.rule_repo.list_by_tenant = AsyncMock(return_value=[
        type(
            "Rule",
            (),
            {
                "resource_type": "instance",
                "resource_id": collection_id,
                "effect": "allow",
            },
        )(),
    ])
    service.rule_repo.list_by_user = AsyncMock(return_value=[])

    async def _fake_batch_resolve(_session, resource_type, resource_ids):
        assert resource_type == "instance"
        assert resource_ids == {collection_id}
        return {collection_id: ("docs", "collection")}

    monkeypatch.setattr(
        permission_service_module,
        "_batch_resolve_resource_targets",
        _fake_batch_resolve,
    )

    perms = await service.resolve_permissions(
        tenant_id=tenant_id,
        default_collection_allow=False,
    )

    assert perms.is_collection_allowed("docs") is True
    assert perms.collection_permissions["docs"] is True
