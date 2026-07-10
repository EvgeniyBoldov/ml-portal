from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.routers.collections import upload_shared
from app.models.collection import CollectionType


@pytest.mark.asyncio
async def test_resolve_table_collection_by_slug_returns_resolved_tenant_id(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(
        slug="orders",
        collection_type=CollectionType.TABLE.value,
    )
    fake_service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=collection),
        ensure_sql_storage_table=AsyncMock(),
    )

    monkeypatch.setattr(
        upload_shared,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=tenant_id),
    )
    monkeypatch.setattr(
        upload_shared,
        "CollectionService",
        lambda _session: fake_service,
    )

    resolved_collection, resolved_service, resolved_tenant_id = await upload_shared._resolve_table_collection_by_slug(
        slug="orders",
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), tenant_ids=[str(tenant_id)], role="reader"),
        tenant_id=None,
    )

    assert resolved_collection is collection
    assert resolved_service is fake_service
    assert resolved_tenant_id == tenant_id


@pytest.mark.asyncio
async def test_resolve_table_collection_by_slug_bootstraps_sql_storage(monkeypatch):
    tenant_id = uuid4()
    collection = SimpleNamespace(
        slug="warehouse",
        collection_type=CollectionType.SQL.value,
    )
    fake_service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=collection),
        ensure_sql_storage_table=AsyncMock(),
    )

    monkeypatch.setattr(
        upload_shared,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=tenant_id),
    )
    monkeypatch.setattr(
        upload_shared,
        "CollectionService",
        lambda _session: fake_service,
    )

    await upload_shared._resolve_table_collection_by_slug(
        slug="warehouse",
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), tenant_ids=[str(tenant_id)], role="reader"),
        tenant_id=None,
    )

    fake_service.ensure_sql_storage_table.assert_awaited_once_with(collection)
