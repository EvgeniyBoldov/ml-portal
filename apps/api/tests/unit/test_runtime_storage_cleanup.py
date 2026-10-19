from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.runtime_storage_cleanup_service import RuntimeStorageCleanupService


@pytest.mark.asyncio
async def test_cleanup_removes_abandoned_objects_and_keeps_live_and_recent(monkeypatch):
    from app.services import runtime_storage_cleanup_service as module
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=1)
    objects = {"runtime-context/": [
        {"Key": "runtime-context/live", "LastModified": old},
        {"Key": "runtime-context/abandoned", "LastModified": old},
        {"Key": "runtime-context/pending", "LastModified": now}]}

    async def iterate(bucket, prefix):
        for item in objects.get(prefix, []):
            yield item

    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(
        S3_BUCKET_CHAT_UPLOADS="test", S3_BUCKET_RAG="test", S3_BUCKET_ARTIFACTS="test"))
    monkeypatch.setattr(module, "s3_manager", SimpleNamespace(iter_objects=iterate, delete_object=delete))
    service = RuntimeStorageCleanupService(MagicMock())

    async def referenced(bucket, key):
        return key == "runtime-context/live"

    service.repository.referenced = referenced
    assert await service.cleanup(older_than=now - timedelta(hours=1)) == 1
    delete.assert_awaited_once_with("test", "runtime-context/abandoned")


@pytest.mark.asyncio
async def test_object_iteration_visits_all_pages_without_silently_skipping_failure():
    from app.adapters.s3_client import S3Client
    client = S3Client()
    backend = MagicMock()
    backend.list_objects_v2.side_effect = [
        {"Contents": [{"Key": "one"}], "NextContinuationToken": "next"},
        {"Contents": [{"Key": "two"}]}]
    client._get_client = lambda: backend
    assert [item["Key"] async for item in client.iter_objects("test", "prefix")] == ["one", "two"]
    assert backend.list_objects_v2.call_args.kwargs["ContinuationToken"] == "next"
