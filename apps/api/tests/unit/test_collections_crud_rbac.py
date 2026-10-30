from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.services.permission_service import EffectivePermissions
from app.services.collection_public_service import CollectionPublicService
from app.schemas.collections_public import CollectionCapabilities
from app.api.v1.routers.collections import crud as collections_crud


def _fake_collection(slug: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        lifecycle_status="active",
        collection_type="table",
        slug=slug,
        name=slug,
        description=None,
        fields=[],
        total_rows=0,
        is_active=True,
        has_vector_search=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("collection_type", ["api", "sql"])
async def test_external_collection_response_uses_safe_metadata_without_local_count(collection_type):
    collection = _fake_collection("external")
    collection.collection_type = collection_type
    collection.current_version = SimpleNamespace(
        status="published",
        version=3,
        data_description="Published source description",
        usage_purpose="Published purpose",
    )
    collection.data_instance = SimpleNamespace(name="Jira Prod")
    service = SimpleNamespace(
        sync_collection_status=AsyncMock(),
        get_effective_total_rows=AsyncMock(),
    )

    response = await collections_crud._build_collection_response(service, collection)

    assert response.status == "unknown"
    assert response.status_details is None
    assert response.total_rows == 0  # Legacy field remains for existing clients.
    assert response.count.value is None
    assert response.count.kind is None
    assert response.source.model_dump() == {"name": "Jira Prod", "type": collection_type}
    assert response.description == "Published source description"
    assert response.purpose == "Published purpose"
    assert response.version.model_dump() == {"number": 3, "status": "published"}
    service.sync_collection_status.assert_not_awaited()
    service.get_effective_total_rows.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_collection_response_omits_unpublished_metadata_and_unsafe_source_name():
    collection = _fake_collection("external")
    collection.collection_type = "api"
    collection.current_version = SimpleNamespace(
        status="draft",
        version=4,
        data_description="Draft text must not be shown",
        usage_purpose="Draft purpose must not be shown",
    )
    collection.data_instance = SimpleNamespace(name="https://private.example/token")
    service = SimpleNamespace(
        sync_collection_status=AsyncMock(),
        get_effective_total_rows=AsyncMock(),
    )

    response = await collections_crud._build_collection_response(service, collection)

    assert response.source.name == "Внешний источник"
    assert response.description is None
    assert response.purpose is None
    assert response.version is None


@pytest.mark.asyncio
async def test_local_collection_response_preserves_status_and_known_count():
    collection = _fake_collection("local")
    service = SimpleNamespace(
        sync_collection_status=AsyncMock(return_value={"status": "ready", "details": {"source": "local"}}),
        get_effective_total_rows=AsyncMock(return_value=7),
    )

    response = await collections_crud._build_collection_response(service, collection)

    assert response.status == "ready"
    assert response.status_details == {"source": "local"}
    assert response.total_rows == 7
    assert response.count.model_dump() == {"value": 7, "kind": "rows", "unit": "строк"}


@pytest.mark.asyncio
async def test_list_collections_filters_denied_by_rbac(monkeypatch):
    allowed = _fake_collection("allowed")
    denied = _fake_collection("denied")
    fake_service = SimpleNamespace(
        session=AsyncMock(),
        list_collections=AsyncMock(return_value=[allowed, denied]),
        sync_collection_status=AsyncMock(return_value={"status": "ready", "details": {}}),
        get_effective_total_rows=AsyncMock(return_value=0),
    )

    async def capabilities(_self, _collection, *, user_id, collection_allowed=True):
        return CollectionCapabilities(view_content=collection_allowed), {}

    monkeypatch.setattr(CollectionPublicService, "build_capabilities", capabilities)

    monkeypatch.setattr(
        collections_crud,
        "CollectionService",
        lambda _session: fake_service,
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_collection_permissions",
        AsyncMock(
            return_value=EffectivePermissions(
                collection_permissions={"allowed": True, "denied": False},
                default_collection_allow=False,
            )
        ),
    )

    response = await collections_crud.list_collections(
        active_only=True,
        tenant_id=None,
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="reader"),
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].slug == "allowed"


@pytest.mark.asyncio
async def test_get_collection_returns_404_when_denied_by_rbac(monkeypatch):
    denied = _fake_collection("denied")
    tenant_id = uuid4()
    denied.tenant_id = tenant_id
    fake_service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=denied),
        sync_collection_status=AsyncMock(return_value={"status": "ready", "details": {}}),
        get_effective_total_rows=AsyncMock(return_value=0),
    )

    monkeypatch.setattr(
        collections_crud,
        "CollectionService",
        lambda _session: fake_service,
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=tenant_id),
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_collection_permissions",
        AsyncMock(
            return_value=EffectivePermissions(
                collection_permissions={"denied": False},
                default_collection_allow=False,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await collections_crud.get_collection(
            slug="denied",
            tenant_id=None,
            session=AsyncMock(),
            user=SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="reader"),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("is_platform_admin", [False, True])
async def test_collection_workspaces_endpoint_uses_member_or_platform_scope(is_platform_admin):
    tenant_id = uuid4()
    user_id = uuid4()
    session = AsyncMock()
    session.scalar.return_value = is_platform_admin

    class Result:
        def all(self):
            return [(tenant_id, "Workspace")]

    session.execute.return_value = Result()
    response = await collections_crud.list_collection_workspaces(
        session=session,
        user=SimpleNamespace(id=user_id),
    )

    assert len(response.items) == 1
    assert response.items[0].id == tenant_id
    assert response.items[0].name == "Workspace"
    query = str(session.execute.await_args.args[0]).lower()
    assert "tenants.is_active" in query
    assert "lifecycle_status" in query
    assert ("join user_tenants" in query) is (not is_platform_admin)
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_collection_detail_exposes_inactive_capability_reasons(monkeypatch):
    tenant_id = uuid4()
    collection = _fake_collection("inactive")
    collection.tenant_id = tenant_id
    collection.is_active = False
    collection.lifecycle_status = "deprecated"
    session = AsyncMock()
    service = SimpleNamespace(
        session=session,
        get_by_slug=AsyncMock(return_value=collection),
        sync_collection_status=AsyncMock(return_value={"status": "created", "details": {}}),
        get_effective_total_rows=AsyncMock(return_value=0),
    )
    monkeypatch.setattr(collections_crud, "CollectionService", lambda _session: service)
    monkeypatch.setattr(collections_crud, "_resolve_requested_tenant_id", AsyncMock(return_value=tenant_id))
    monkeypatch.setattr(collections_crud, "require_collection_permission", AsyncMock())

    async def capabilities(_self, _collection, *, user_id, collection_allowed=False):
        return (
            CollectionCapabilities(view_content=collection_allowed, can_edit_content=True),
            {"upload_csv": "collection_inactive", "mutate_rows": "collection_inactive"},
        )

    monkeypatch.setattr(CollectionPublicService, "build_capabilities", capabilities)
    user = SimpleNamespace(id=uuid4(), role="editor", tenant_ids=[str(tenant_id)])

    response = await collections_crud.get_collection(
        slug="inactive", tenant_id=tenant_id, session=session, user=user,
    )

    service.get_by_slug.assert_awaited_once_with("inactive", include_inactive=True)
    assert response.tenant_id == tenant_id
    assert response.capabilities.can_edit_content
    assert not response.capabilities.upload_csv
    assert response.capability_reasons["upload_csv"] == "collection_inactive"
