from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.file_delivery_service import FileDeliveryNotFoundError, FileDeliveryService


@pytest.mark.asyncio
async def test_resolve_collection_export_success(monkeypatch):
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    export_id = str(uuid.uuid4())
    meta = {
        "status": "ready",
        "tenant_id": str(tenant_id),
        "owner_id": str(owner_id),
        "bucket": "artifacts",
        "key": f"tenants/{tenant_id}/exports/{export_id}.csv",
        "file_name": "collection_export.csv",
        "content_type": "text/csv",
        "size_bytes": 128,
    }

    cache = SimpleNamespace(get=AsyncMock(return_value=meta))

    async def _fake_get_cache():
        return cache

    monkeypatch.setattr("app.services.file_delivery_service.get_cache", _fake_get_cache)

    service = FileDeliveryService(
        session=AsyncMock(),
        repo_factory=SimpleNamespace(tenant_id=tenant_id),
    )
    file_id = FileDeliveryService.make_collection_export_file_id(export_id)
    resolved = await service.resolve(file_id, owner_id=str(owner_id))
    assert resolved.bucket == "artifacts"
    assert resolved.content_type == "text/csv"
    assert resolved.file_name == "collection_export.csv"


@pytest.mark.asyncio
async def test_resolve_collection_export_rejects_wrong_owner(monkeypatch):
    tenant_id = uuid.uuid4()
    export_id = str(uuid.uuid4())
    meta = {
        "status": "ready",
        "tenant_id": str(tenant_id),
        "owner_id": str(uuid.uuid4()),
        "bucket": "artifacts",
        "key": f"tenants/{tenant_id}/exports/{export_id}.csv",
    }

    cache = SimpleNamespace(get=AsyncMock(return_value=meta))

    async def _fake_get_cache():
        return cache

    monkeypatch.setattr("app.services.file_delivery_service.get_cache", _fake_get_cache)

    service = FileDeliveryService(
        session=AsyncMock(),
        repo_factory=SimpleNamespace(tenant_id=tenant_id),
    )
    file_id = FileDeliveryService.make_collection_export_file_id(export_id)
    with pytest.raises(FileDeliveryNotFoundError):
        await service.resolve(file_id, owner_id=str(uuid.uuid4()))
