from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import json

import pytest

from app.services.artifact_representation_service import ArtifactRepresentationService
from app.services.chat_artifact_reference_service import ChatArtifactAccessDenied


@pytest.fixture
def setup(monkeypatch):
    from app.services import artifact_representation_service as module
    session = MagicMock(execute=AsyncMock(), flush=AsyncMock(), get=AsyncMock(return_value=None))
    storage = SimpleNamespace(get_object=AsyncMock(return_value=b"source"), upload_fileobj=AsyncMock(return_value=True))
    resolve = AsyncMock(return_value=SimpleNamespace(bucket="test", key="source", file_name="a.txt", content_type="text/plain"))
    extract = AsyncMock(return_value=SimpleNamespace(content_kind="text", text="extracted", truncated=True, parser="test", warnings=["partial"]))
    monkeypatch.setattr(module, "s3_manager", storage)
    monkeypatch.setattr(module, "ChatArtifactReferenceService", lambda _: SimpleNamespace(resolve=resolve))
    monkeypatch.setattr(module, "DocumentExtractionService", lambda: SimpleNamespace(extract=extract))
    service = ArtifactRepresentationService(session)
    service.repository.find = AsyncMock(return_value=None)
    return service, storage, resolve, extract


@pytest.mark.asyncio
async def test_read_persists_actual_completeness_and_reuses_extraction(setup):
    service, storage, resolve, extract = setup
    args = dict(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    first = await service.read(**args)
    assert first["truncated"] and first["status"] == "partial"
    row = service.session.add.call_args.args[0]
    assert "content" not in row.details
    service.repository.find.return_value = row
    storage.get_object.side_effect = [b"source", json.dumps({k: v for k, v in first.items() if k not in {"representation_id", "reused"}}).encode()]
    second = await service.read(**args)
    assert second["reused"] and second["representation_id"] == first["representation_id"]
    assert second["content"] == first["content"]
    assert resolve.await_count == 2
    extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_conversion_never_bypasses_access(setup):
    service, storage, resolve, extract = setup
    resolve.side_effect = ChatArtifactAccessDenied("denied")
    with pytest.raises(ChatArtifactAccessDenied):
        await service.read(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    storage.get_object.assert_not_awaited()
    extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_change_changes_cache_identity(setup):
    service, storage, _, extract = setup
    args = dict(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    first = await service.read(**args)
    storage.get_object.return_value = b"changed"
    second = await service.read(**args)
    assert first["source_fingerprint"] != second["source_fingerprint"]
    assert extract.await_count == 2


@pytest.mark.asyncio
async def test_storage_failure_does_not_register_representation(setup):
    service, storage, _, _ = setup
    storage.upload_fileobj.return_value = False
    with pytest.raises(ValueError):
        await service.read(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    service.session.add.assert_not_called()


@pytest.mark.asyncio
async def test_canonical_is_complete_and_has_a_separate_cache_identity(setup):
    service, storage, resolve, extract = setup
    resolve.return_value.size_bytes = 6
    extract.return_value.text = "long document\n" * 4000
    extract.return_value.truncated = False
    extract.return_value.meta = {}
    scope = dict(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    first = await service.canonical(**scope)
    assert len(first["content"]) > 32000 and first["source_complete"]
    assert extract.await_args.args[0].profile == "rag_ingest"
    row = service.session.add.call_args.args[0]
    assert row.extraction_key.startswith("file_data:")
    assert "content" not in row.details
    service.repository.find.return_value = row
    storage.get_object.side_effect = [b"source", json.dumps({key: value for key, value in first.items()
        if key not in {"representation_id", "reused"}}).encode()]
    second = await service.canonical(**scope)
    assert second["reused"] and second["representation_id"] == first["representation_id"]
    assert resolve.await_count == 2 and extract.await_count == 1


@pytest.mark.asyncio
async def test_search_cannot_create_a_missing_canonical_representation(setup):
    service, storage, resolve, extract = setup
    resolve.return_value.size_bytes = 6
    scope = dict(artifact_id=str(uuid4()), chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=None)
    assert await service.canonical(**scope, extract=False) is None
    extract.assert_not_awaited()
    storage.upload_fileobj.assert_not_awaited()
    resolve.side_effect = ChatArtifactAccessDenied("revoked")
    with pytest.raises(ChatArtifactAccessDenied):
        await service.canonical(**scope, extract=False)
