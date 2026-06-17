from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.routers.collections import templates as templates_router


@pytest.mark.asyncio
async def test_delete_templates_deletes_rows_and_refreshes_status(monkeypatch):
    collection_id = uuid4()
    row_ids = [uuid4(), uuid4()]

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=uuid4(),
        collection_type="template",
    )
    resolve_mock = AsyncMock(return_value=fake_collection)
    monkeypatch.setattr(templates_router, "_resolve_template_collection", resolve_mock)

    fake_row_service = MagicMock()
    fake_row_service.delete_rows = AsyncMock(return_value=len(row_ids))
    monkeypatch.setattr(templates_router, "CollectionRowService", lambda _session: fake_row_service)

    fake_snapshot_service = MagicMock()
    fake_snapshot_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(
        templates_router,
        "CollectionStatusSnapshotService",
        lambda _session: fake_snapshot_service,
    )

    session = AsyncMock()
    result = await templates_router.delete_templates(
        collection_id=collection_id,
        ids=row_ids,
        session=session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    resolve_mock.assert_awaited_once()
    fake_row_service.delete_rows.assert_awaited_once_with(fake_collection, row_ids)
    fake_snapshot_service.sync_collection_status.assert_awaited_once_with(fake_collection, persist=False)
    session.commit.assert_awaited_once()
    assert result == {
        "deleted": 2,
        "ids": [str(row_id) for row_id in row_ids],
    }
