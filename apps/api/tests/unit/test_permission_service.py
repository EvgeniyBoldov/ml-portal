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
async def test_permission_service_resolve_permissions_from_legacy_sets():
    service = PermissionService(session=AsyncMock())

    default_set = type(
        "PS",
        (),
        {
            "scope": "default",
            "collection_permissions": {"docs": "allowed", "secrets": "denied"},
        },
    )()
    tenant_set = type(
        "PS",
        (),
        {
            "scope": "tenant",
            "collection_permissions": {"docs": "denied"},
        },
    )()
    user_set = type(
        "PS",
        (),
        {
            "scope": "user",
            "collection_permissions": {"docs": "allowed"},
        },
    )()

    service.repo.get_all_for_context = AsyncMock(return_value=[default_set, tenant_set, user_set])
    service._apply_rbac_rules = AsyncMock()

    perms = await service.resolve_permissions()

    assert perms.is_collection_allowed("docs") is True
    assert perms.is_collection_allowed("secrets") is False
    service._apply_rbac_rules.assert_awaited_once()


@pytest.mark.asyncio
async def test_permission_service_maps_legacy_instance_rules_to_collection_permissions(monkeypatch):
    service = PermissionService(session=AsyncMock())
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

    perms = await service.resolve_permissions(default_collection_allow=False)

    assert perms.is_collection_allowed("docs") is True
    assert perms.collection_permissions["docs"] is True
