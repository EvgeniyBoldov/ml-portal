from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.collections import crud, stream_shared, templates, upload_shared
from app.services import collection_service
from app.services.permission_service import EffectivePermissions


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["table", "sql", "api", "document", "template", "stream"])
@pytest.mark.parametrize("role", ["user", "admin"])
async def test_data_paths_reject_a_denied_collection_before_accessing_storage(monkeypatch, kind, role):
    tenant_id = uuid4()
    collection = SimpleNamespace(id=uuid4(), slug="denied", tenant_id=tenant_id,
                                 collection_type="document" if kind == "stream" else kind)
    service = SimpleNamespace(get_by_slug=AsyncMock(return_value=collection),
                              get_by_id=AsyncMock(return_value=collection),
                              ensure_sql_storage_table=AsyncMock(), ensure_contract_fields_present=AsyncMock())
    monkeypatch.setattr(upload_shared, "CollectionService", lambda session: service)
    monkeypatch.setattr(collection_service, "CollectionService", lambda session: service)
    monkeypatch.setattr(upload_shared, "_resolve_requested_tenant_id", AsyncMock(return_value=tenant_id))
    monkeypatch.setattr(upload_shared, "_resolve_user_tenants", AsyncMock(return_value=[tenant_id]))
    monkeypatch.setattr(crud, "_resolve_collection_permissions", AsyncMock(return_value=EffectivePermissions(
        collection_permissions={"denied": False}, default_collection_allow=True)))
    user = SimpleNamespace(id=str(uuid4()), tenant_ids=[str(tenant_id)], role=role)
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        if kind in {"table", "sql", "api"}:
            await upload_shared._resolve_table_collection_by_slug("denied", session, user, None)
        elif kind == "document":
            await upload_shared._resolve_collection(collection.id, session, user)
        elif kind == "template":
            await templates._resolve_template_collection(collection.id, session, user)
        else:
            await stream_shared._resolve_document_collection(collection.id, session, user)
    assert exc.value.status_code == 404
    service.ensure_sql_storage_table.assert_not_awaited()
    service.ensure_contract_fields_present.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_access_uses_active_memberships_instead_of_stale_token(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(id=uuid4(), slug="documents", tenant_id=tenant_id, collection_type="document")
    service = SimpleNamespace(get_by_id=AsyncMock(return_value=collection))
    monkeypatch.setattr(upload_shared, "CollectionService", lambda session: service)
    monkeypatch.setattr(upload_shared, "_resolve_user_tenants", AsyncMock(return_value=[]))
    user = SimpleNamespace(id=str(uuid4()), tenant_ids=[str(tenant_id)], role="user")
    with pytest.raises(HTTPException):
        await upload_shared._resolve_collection(collection.id, AsyncMock(), user)


@pytest.mark.asyncio
async def test_document_access_accepts_an_active_secondary_membership_and_checks_policy(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(id=uuid4(), slug="documents", tenant_id=tenant_id, collection_type="document")
    monkeypatch.setattr(upload_shared, "CollectionService", lambda session: SimpleNamespace(get_by_id=AsyncMock(return_value=collection)))
    monkeypatch.setattr(upload_shared, "_resolve_user_tenants", AsyncMock(return_value=[uuid4(), tenant_id]))
    permissions = AsyncMock(return_value=EffectivePermissions(collection_permissions={"documents": True}, default_collection_allow=False))
    monkeypatch.setattr(crud, "_resolve_collection_permissions", permissions)
    user = SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="user")
    result = await upload_shared._resolve_collection(collection.id, AsyncMock(), user)
    assert result is collection
    assert permissions.await_args.kwargs["tenant_id"] == tenant_id


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [crud, upload_shared])
async def test_explicit_tenant_does_not_grant_membership_to_a_user_without_tenants(monkeypatch, module):
    monkeypatch.setattr(module, "_resolve_user_tenants", AsyncMock(return_value=[]))
    user = SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="user")
    with pytest.raises(HTTPException) as exc:
        await module._resolve_requested_tenant_id(AsyncMock(), user, uuid4())
    assert exc.value.status_code == 403
