from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.collections import documents, templates, upload_shared
from app.api.v1.routers.collections.stream_shared import DocumentMembership
from app.services import collection_service as collection_service_module


@pytest.mark.asyncio
async def test_document_collection_delete_preflights_shared_acl_before_side_effects(monkeypatch):
    collection = SimpleNamespace(tenant_id=uuid4(), collection_type="document")
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    document_id = uuid4()
    membership = DocumentMembership(source=SimpleNamespace(meta={}), in_tenant=True, in_collection=True)

    monkeypatch.setattr(documents, "_resolve_collection", AsyncMock(return_value=collection))
    monkeypatch.setattr(documents, "_require_collection_editor", AsyncMock())
    monkeypatch.setattr(documents, "_resolve_document_membership", AsyncMock(return_value=membership))
    shared_acl_guard = AsyncMock(side_effect=HTTPException(status_code=404, detail="Document not found"))
    monkeypatch.setattr(documents, "require_document_content_access", shared_acl_guard)
    stop_ingest = AsyncMock()
    monkeypatch.setattr(documents, "_stop_pipeline_and_revoke", stop_ingest)

    with pytest.raises(HTTPException) as denied:
        await documents.delete_collection_documents(
            collection_id=uuid4(),
            doc_ids=[str(document_id)],
            session=session,
            user=user,
        )

    assert denied.value.status_code == 404
    shared_acl_guard.assert_awaited_once_with(
        session,
        user,
        document_id=document_id,
        tenant_id=collection.tenant_id,
    )
    stop_ingest.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_table_write_permission_denial_precedes_sql_storage_ddl(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(
        tenant_id=tenant_id,
        collection_type="sql",
        is_active=True,
        lifecycle_status="active",
    )
    service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=collection),
        ensure_sql_storage_table=AsyncMock(),
    )
    session = AsyncMock()
    monkeypatch.setattr(upload_shared, "_resolve_requested_tenant_id", AsyncMock(return_value=tenant_id))
    monkeypatch.setattr(upload_shared, "CollectionService", lambda _session: service)
    monkeypatch.setattr(upload_shared, "require_collection_permission", AsyncMock())
    monkeypatch.setattr(
        upload_shared,
        "_require_collection_editor",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="denied")),
    )

    with pytest.raises(HTTPException) as denied:
        await upload_shared._resolve_table_collection_by_slug(
            "external", session, SimpleNamespace(id=uuid4()), tenant_id, for_write=True,
        )

    assert denied.value.status_code == 403
    service.ensure_sql_storage_table.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_table_remains_readable_but_write_is_rejected(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(
        tenant_id=tenant_id,
        collection_type="table",
        is_active=False,
        lifecycle_status="deprecated",
    )
    service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=collection),
        ensure_sql_storage_table=AsyncMock(),
    )
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(upload_shared, "_resolve_requested_tenant_id", AsyncMock(return_value=tenant_id))
    monkeypatch.setattr(upload_shared, "CollectionService", lambda _session: service)
    monkeypatch.setattr(upload_shared, "require_collection_permission", AsyncMock())

    read_collection, _, _ = await upload_shared._resolve_table_collection_by_slug(
        "archived", session, user, tenant_id,
    )
    assert read_collection is collection
    service.get_by_slug.assert_awaited_with("archived", include_inactive=True)

    monkeypatch.setattr(
        upload_shared,
        "_require_collection_editor",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="Collection is inactive")),
    )
    with pytest.raises(HTTPException) as denied:
        await upload_shared._resolve_table_collection_by_slug(
            "archived", session, user, tenant_id, for_write=True,
        )
    assert denied.value.status_code == 409
    service.ensure_sql_storage_table.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_write_permission_denial_precedes_schema_healing(monkeypatch):
    collection = SimpleNamespace(collection_type="template", tenant_id=uuid4())
    service = SimpleNamespace(ensure_contract_fields_present=AsyncMock())
    session = AsyncMock()
    monkeypatch.setattr(collection_service_module, "CollectionService", lambda _session: service)
    monkeypatch.setattr(
        upload_shared,
        "_resolve_collection",
        AsyncMock(return_value=collection),
    )
    monkeypatch.setattr(
        upload_shared,
        "_require_collection_editor",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="denied")),
    )

    with pytest.raises(HTTPException) as denied:
        await templates._resolve_template_collection(
            uuid4(), session, SimpleNamespace(id=uuid4()), for_write=True,
        )

    assert denied.value.status_code == 403
    service.ensure_contract_fields_present.assert_not_awaited()
