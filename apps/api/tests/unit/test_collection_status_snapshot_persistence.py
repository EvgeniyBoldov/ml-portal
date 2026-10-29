from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService


@pytest.mark.asyncio
async def test_read_only_status_snapshot_does_not_dirty_or_flush_collection():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    service = CollectionStatusSnapshotService(session)
    service.get_status_snapshot = AsyncMock(return_value={"status": "ready", "details": {}})
    collection = SimpleNamespace(status="created")

    snapshot = await service.sync_collection_status(collection, persist=False)

    assert snapshot["status"] == "ready"
    assert collection.status == "created"
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_persisted_status_snapshot_updates_and_flushes_collection():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    service = CollectionStatusSnapshotService(session)
    service.get_status_snapshot = AsyncMock(return_value={"status": "ready", "details": {}})
    collection = SimpleNamespace(status="created")

    await service.sync_collection_status(collection)

    assert collection.status == "ready"
    session.add.assert_called_once_with(collection)
    session.flush.assert_awaited_once()
