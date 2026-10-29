from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.collections import crud
from app.services.collection_public_service import (
    CollectionPublicService,
    build_collection_display_metadata,
    safe_public_fields,
)


def collection(kind='table', published=True):
    return SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), slug='navigation-only', name='Планы',
        collection_type=kind, is_active=True, lifecycle_status='active', table_name='coll_plans',
        description='PRIVATE legacy description', source_contract={'url': 'https://secret.example', 'password': 'SECRET'},
        data_instance=SimpleNamespace(name='Источник данных', url='https://secret.example', headers={'Authorization': 'SECRET'}),
        current_version=SimpleNamespace(version=2, status='published' if published else 'draft',
            data_description='Опубликованное описание', usage_purpose='Для подготовки планов', notes='SECRET',
            retrieval_params={'token': 'SECRET'}),
        fields=[{'name': 'title', 'data_type': 'text', 'required': True, 'category': 'user', 'default': 'PRIVATE'},
                {'name': 'api_token', 'data_type': 'text'}, {'name': 'connection_url', 'data_type': 'text'},
                {'name': '_internal', 'data_type': 'text'}, {'name': 'runtime', 'data_type': 'json', 'category': 'system'}],
    )


def projection(*, editable=False, materialized=True):
    session = AsyncMock()
    service = CollectionPublicService(session)
    service.can_edit = AsyncMock(return_value=editable)
    service._materialized = AsyncMock(return_value=materialized)
    collections = SimpleNamespace(
        count=AsyncMock(return_value=7), get_effective_total_rows=AsyncMock(return_value=3),
        status_snapshot=SimpleNamespace(get_status_snapshot=AsyncMock(return_value={'status': 'ready'})),
        ensure_contract_fields_present=AsyncMock(), sync_collection_status=AsyncMock(),
    )
    return service, collections, session


@pytest.mark.asyncio
async def test_public_projection_is_allowlisted_and_only_uses_published_version():
    service, host, session = projection()
    response = await service.build(collection(), user_id=str(uuid4()), collection_service=host)
    body = response.model_dump_json()
    assert response.description == 'Опубликованное описание'
    assert response.purpose == 'Для подготовки планов'
    assert response.version.number == 2
    assert [field.name for field in response.fields] == ['title']
    assert response.count.value == 7 and response.count.kind == 'rows'
    for forbidden in ['SECRET', 'PRIVATE', 'headers', 'source_contract', 'retrieval_params', 'notes', 'https://']:
        assert forbidden not in body
    assert not response.capabilities.mutate_rows
    host.ensure_contract_fields_present.assert_not_called()
    host.sync_collection_status.assert_not_called()
    session.add.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_draft_semantics_never_fall_back_to_unpublished_or_legacy_metadata():
    service, host, _ = projection()
    response = await service.build(collection(published=False), user_id=str(uuid4()), collection_service=host)
    assert response.description is None and response.purpose is None and response.version is None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['sql', 'api'])
async def test_external_sources_never_expose_local_catalog_as_content(kind):
    service, host, _ = projection(editable=True)
    response = await service.build(collection(kind), user_id=str(uuid4()), collection_service=host)
    assert response.locality == 'remote'
    assert response.count.value is None and response.count.unit is None
    assert response.readiness.status == 'unknown'
    assert not any(response.capabilities.model_dump().values())
    assert response.fields == []
    host.count.assert_not_called()
    service._materialized.assert_not_called()


@pytest.mark.asyncio
async def test_missing_local_storage_disables_preview_without_bootstrap():
    service, host, _ = projection(editable=True, materialized=False)
    response = await service.build(collection(), user_id=str(uuid4()), collection_service=host)
    assert not response.capabilities.view_content
    assert response.capability_reasons['view_content'] == 'storage_unavailable'
    assert response.count.value is None
    host.count.assert_not_called()
    host.ensure_contract_fields_present.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,action', [('table', 'mutate_rows'), ('document', 'ingest'), ('template', 'approve_templates')])
@pytest.mark.parametrize('editable', [False, True])
async def test_action_capabilities_use_current_editor_resolution(kind, action, editable):
    service, host, _ = projection(editable=editable)
    response = await service.build(collection(kind), user_id=str(uuid4()), collection_service=host)
    assert getattr(response.capabilities, action) is editable
    service.can_edit.assert_awaited_once()
    assert response.capabilities.view_content


@pytest.mark.asyncio
async def test_workspace_is_explicit_and_authorized_without_default_selection(monkeypatch):
    resolver = AsyncMock(return_value=[uuid4()])
    monkeypatch.setattr(crud, '_resolve_user_tenants', resolver)
    with pytest.raises(HTTPException) as missing:
        await crud._resolve_requested_tenant_id(AsyncMock(), SimpleNamespace(id=str(uuid4())), None)
    assert missing.value.status_code == 400
    resolver.assert_not_called()
    with pytest.raises(HTTPException) as denied:
        await crud._resolve_requested_tenant_id(AsyncMock(), SimpleNamespace(id=str(uuid4())), uuid4())
    assert denied.value.status_code == 403


def test_source_schema_is_local_and_structural_only():
    assert [field.model_dump() for field in safe_public_fields(collection())] == [
        {'name': 'title', 'data_type': 'text', 'required': True},
    ]
    assert safe_public_fields(collection('sql')) == []


@pytest.mark.parametrize('source_name', [
    'postgresql://user:password@example/database',
    'Jira\nProd',
    'Netbox\x7f',
])
def test_display_metadata_rejects_connection_strings_and_control_characters(source_name):
    item = collection('api')
    item.data_instance.name = source_name

    metadata = build_collection_display_metadata(item)

    assert metadata.source.name == 'Внешний источник'
    assert metadata.source.type == 'api'
