from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import collection_content_access_service as access_module
from app.services.collection_content_access_service import CollectionContentAccessService


class QueryResult:
    def __init__(self, *, row=None, rows=()):
        self._row = row
        self._rows = list(rows)

    def one_or_none(self):
        return self._row

    def all(self):
        return self._rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_active,lifecycle_status,is_tenant_admin,is_data_editor,expected",
    [
        (True, "active", True, False, None),
        (True, "active", False, True, None),
        (True, "active", False, False, "editing_permission_required"),
        (False, "active", True, True, "tenant_inactive"),
        (True, "deprecated", True, True, "tenant_inactive"),
    ],
)
async def test_edit_access_requires_active_tenant_and_tenant_editor_role(
    tenant_active, lifecycle_status, is_tenant_admin, is_data_editor, expected
):
    session = AsyncMock()
    session.execute.return_value = QueryResult(
        row=SimpleNamespace(
            is_active=tenant_active,
            lifecycle_status=lifecycle_status,
            is_tenant_admin=is_tenant_admin,
            is_data_editor=is_data_editor,
        )
    )
    service = CollectionContentAccessService(session)

    actual = await service.edit_access_reason(uuid4(), uuid4())

    assert actual == expected


@pytest.mark.asyncio
async def test_linked_document_requires_access_to_every_collection(monkeypatch):
    tenant_id = uuid4()
    rows = [
        (tenant_id, tenant_id, "visible", True, "active"),
        (tenant_id, tenant_id, "denied", True, "active"),
    ]
    session = AsyncMock()
    session.execute.side_effect = [
        QueryResult(rows=rows),
        QueryResult(row=SimpleNamespace(
            is_active=True,
            lifecycle_status="active",
            is_tenant_admin=False,
            is_data_editor=True,
        )),
    ]

    class Resolver:
        def __init__(self, _permissions):
            self.checked = []

        async def resolve_effective_permissions(self, **_kwargs):
            return object()

        def is_collection_allowed(self, *, effective_permissions, collection_slug):
            self.checked.append(collection_slug)
            return collection_slug != "denied"

    resolver = Resolver(None)
    monkeypatch.setattr(access_module, "RuntimeRbacResolver", lambda _permissions: resolver)
    service = CollectionContentAccessService(session)

    result = await service.document_write_access(
        user_id=uuid4(), document_id=uuid4(), document_tenant_id=tenant_id,
    )

    assert result.linked_to_collection
    assert not result.allowed
    assert result.reason == "collection_access_denied"
    assert resolver.checked == ["visible", "denied"]


@pytest.mark.asyncio
async def test_linked_document_with_mismatched_membership_is_denied_before_role_lookup():
    session = AsyncMock()
    session.execute.return_value = QueryResult(rows=[(uuid4(), uuid4(), "collection")])
    service = CollectionContentAccessService(session)

    result = await service.document_write_access(
        user_id=uuid4(), document_id=uuid4(), document_tenant_id=uuid4(),
    )

    assert result.linked_to_collection
    assert not result.allowed
    assert result.reason == "collection_membership_mismatch"
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_standalone_document_does_not_inherit_collection_editor_policy():
    session = AsyncMock()
    session.execute.return_value = QueryResult(rows=[])
    service = CollectionContentAccessService(session)

    result = await service.document_write_access(
        user_id=uuid4(), document_id=uuid4(), document_tenant_id=uuid4(),
    )

    assert not result.linked_to_collection
    assert result.allowed
    assert result.reason is None
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_linked_document_inactive_collection_is_not_mutable():
    tenant_id = uuid4()
    session = AsyncMock()
    session.execute.side_effect = [
        QueryResult(rows=[(tenant_id, tenant_id, "archived", False, "active")]),
        QueryResult(row=SimpleNamespace(
            is_active=True,
            lifecycle_status="active",
            is_tenant_admin=False,
            is_data_editor=True,
        )),
    ]
    service = CollectionContentAccessService(session)

    result = await service.document_write_access(
        user_id=uuid4(), document_id=uuid4(), document_tenant_id=tenant_id,
    )

    assert result.linked_to_collection
    assert not result.allowed
    assert result.reason == "collection_inactive"
