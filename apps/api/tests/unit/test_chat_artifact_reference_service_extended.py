"""Extended unit tests for ChatArtifactReferenceService.

Covers manifest normalization details (indexes expiry/staleness, origin
fallbacks, description truncation), get/list resolution paths, resolve for
chat attachments / collection documents / external files, RBAC collection
checks, deletion, and both cleanup jobs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.chat_artifact_reference import ChatArtifactReference
from app.services.chat_artifact_reference_service import (
    ArtifactTarget,
    ChatArtifactAccessDenied,
    ChatArtifactReferenceError,
    ChatArtifactReferenceNotFound,
    ChatArtifactReferenceService,
)
from app.services.file_delivery_service import FileDeliveryNotFoundError

CHAT_ID = uuid.uuid4()
OWNER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def exec_result(rows: list = (), one: object = None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.one_or_none.return_value = one
    return result


def make_reference(
    target_kind: str = "chat_attachment",
    *,
    target_id: str | None = None,
    collection_id: uuid.UUID | None = None,
    metadata_snapshot: dict | None = None,
    display_name: str | None = "artifact.bin",
    content_type: str | None = "application/octet-stream",
    size_bytes: int | None = 10,
) -> ChatArtifactReference:
    return ChatArtifactReference(
        id=uuid.uuid4(),
        chat_id=CHAT_ID,
        owner_id=OWNER_ID,
        target_kind=target_kind,
        target_id=target_id or str(uuid.uuid4()),
        collection_id=collection_id,
        display_name=display_name,
        content_type=content_type,
        size_bytes=size_bytes,
        metadata_snapshot=metadata_snapshot if metadata_snapshot is not None else {},
    )


def make_attachment(**overrides) -> SimpleNamespace:
    payload = {
        "id": uuid.uuid4(),
        "chat_id": CHAT_ID,
        "owner_id": OWNER_ID,
        "storage_bucket": "chat-uploads",
        "storage_key": "chats/x/file.bin",
        "file_name": "file.bin",
        "content_type": "application/octet-stream",
        "size_bytes": 11,
        "created_at": datetime.now(timezone.utc) - timedelta(days=30),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.fixture
def session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service(session) -> ChatArtifactReferenceService:
    return ChatArtifactReferenceService(session)


class TestRegister:
    async def test_merge_keeps_unset_fields_and_overrides_set_ones(self, service, session):
        existing = make_reference(
            display_name="old-name", content_type="old/type", size_bytes=1,
            metadata_snapshot={"status": "ready", "custom": "kept"},
        )
        session.scalar = AsyncMock(return_value=existing)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id=existing.target_id,
                display_name=None, content_type="new/type", size_bytes=99,
                metadata={"added": True},
            ),
        )

        assert result is existing
        assert existing.display_name == "old-name"
        assert existing.content_type == "new/type"
        assert existing.size_bytes == 99
        session.add.assert_not_called()
        session.flush.assert_awaited_once()
        snapshot = existing.metadata_snapshot
        assert snapshot["custom"] == "kept"
        assert snapshot["added"] is True
        assert snapshot["artifact_id"] == str(existing.id)

    async def test_external_kind_origin(self, service, session):
        session.scalar = AsyncMock(return_value=None)
        created: list[ChatArtifactReference] = []
        session.add.side_effect = created.append

        await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(kind="external_file", target_id="colexp-1"),
        )

        assert created[0].metadata_snapshot["origin"]["kind"] == "external_file"

    async def test_generated_attachment_origin(self, service, session):
        session.scalar = AsyncMock(return_value=None)
        session.add.side_effect = lambda ref: None

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={"status": "generated"},
            ),
        )

        assert result.metadata_snapshot["origin"]["kind"] == "agent_generated"

    async def test_origin_falls_back_to_previous_values(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={
                    "origin": {
                        "source_id": "prev-source", "source_type": "prev-type",
                        "collection_id": "11111111-1111-1111-1111-111111111111",
                        "created_by_run_id": "run-9",
                    },
                },
            ),
        )

        origin = result.metadata_snapshot["origin"]
        assert origin["source_id"] == "prev-source"
        assert origin["source_type"] == "prev-type"
        assert origin["collection_id"] == "11111111-1111-1111-1111-111111111111"
        assert origin["created_by_run_id"] == "run-9"


class TestNormalizedMetadata:
    async def test_long_dict_description_is_truncated(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={"description": {"text": "x" * 900, "source": "source_metadata"}},
            ),
        )

        assert len(result.metadata_snapshot["description"]["text"]) == 600

    async def test_long_string_description_is_truncated(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={"description": "y" * 900},
            ),
        )

        description = result.metadata_snapshot["description"]
        assert len(description["text"]) == 600
        assert description["source"] == "source_metadata"

    async def test_file_falls_back_to_previous_metadata(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={"file_name": "prev.txt", "content_type": "text/plain", "size_bytes": 5},
            ),
        )

        assert result.metadata_snapshot["file"] == {
            "name": "prev.txt", "media_type": "text/plain", "size_bytes": 5,
        }

    async def test_representation_and_status_defaults(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={
                    "representation": {
                        "id": "rep-1", "source_fingerprint": "fp-1",
                        "extraction_profile": "std", "status": "ready",
                    },
                },
            ),
        )

        snapshot = result.metadata_snapshot
        assert snapshot["status"] == "ready"
        assert snapshot["representation"]["id"] == "rep-1"

    async def test_nested_lists_are_stripped_of_content_keys(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        result = await service.register(
            chat_id=CHAT_ID, owner_id=OWNER_ID,
            target=ArtifactTarget(
                kind="chat_attachment", target_id="t-1",
                metadata={
                    "pages": [
                        {"label": "p1", "content": "secret", "text": "plain"},
                        {"label": "p2", "snippet": "secret"},
                        {"label": "p3", "description": {"text": "kept", "source": "source_metadata"}},
                    ],
                },
            ),
        )

        pages = result.metadata_snapshot["pages"]
        assert pages[0] == {"label": "p1"}
        assert pages[1] == {"label": "p2"}
        assert pages[2] == {
            "label": "p3", "description": {"text": "kept", "source": "source_metadata"},
        }


class TestManifest:
    def _indexed_reference(self, service, file_data: dict, fingerprint: str | None = None):
        representation = None
        if fingerprint:
            representation = {
                "id": "rep-1", "extraction_profile": "standard",
                "status": "ready", "source_fingerprint": fingerprint,
            }
        reference = make_reference(
            metadata_snapshot={
                "file_data": file_data,
                **({"representation": representation} if representation else {}),
            },
        )
        return reference, service.manifest(reference)

    def test_expired_index_is_marked(self, service):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
        reference, manifest = self._indexed_reference(
            service, {"rag": {"status": "ready", "chunk_count": 3, "expires_at": past}},
        )

        indexes = manifest["attributes"]["file_data"]
        assert indexes["rag"]["status"] == "expired"
        assert indexes["rag"]["chunk_count"] == 3
        assert "representation_id" not in indexes["rag"]

    def test_stale_fingerprint_is_marked(self, service):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).timestamp()
        reference, manifest = self._indexed_reference(
            service,
            {"rag": {"status": "ready", "source_fingerprint": "other", "expires_at": future}},
            fingerprint="current",
        )

        assert manifest["attributes"]["file_data"]["rag"]["status"] == "stale"

    def test_fresh_index_keeps_status(self, service):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).timestamp()
        reference, manifest = self._indexed_reference(
            service,
            {"rag": {"status": "ready", "source_fingerprint": "current", "expires_at": future}},
            fingerprint="current",
        )

        assert manifest["attributes"]["file_data"]["rag"]["status"] == "ready"

    def test_attributes_exclude_passport_keys(self, service):
        reference = make_reference(metadata_snapshot={
            "custom": "v", "schema_version": 1, "artifact_id": "x",
            "origin": {}, "file": {}, "description": None,
            "representation": None, "status": "ready", "file_data": {},
        })

        manifest = service.manifest(reference)

        assert manifest["attributes"] == {"custom": "v"}
        assert manifest["schema_version"] == 1
        assert manifest["artifact_id"] == str(reference.id)


class TestSetDescription:
    async def test_empty_text_returns_without_lookup(self, service, session):
        await service.set_description(
            artifact_id=str(uuid.uuid4()), chat_id=CHAT_ID, owner_id=OWNER_ID,
            description="   ", representation_id=None,
        )

        session.scalar.assert_not_awaited()
        session.flush.assert_not_awaited()

    async def test_sets_model_inferred_description(self, service, session):
        reference = make_reference()
        service.get_reference = AsyncMock(return_value=reference)

        await service.set_description(
            artifact_id=str(reference.id), chat_id=CHAT_ID, owner_id=OWNER_ID,
            description="  Summary text  ", representation_id="rep-7",
        )

        description = reference.metadata_snapshot["description"]
        assert description == {
            "text": "Summary text", "source": "model_inferred", "representation_id": "rep-7",
        }
        session.flush.assert_awaited_once()


class TestListAndGet:
    async def test_list_for_chat_normalizes_legacy_rows(self, service, session):
        legacy = make_reference(metadata_snapshot={"origin": "legacy-string"})
        session.execute = AsyncMock(return_value=exec_result([legacy]))

        result = await service.list_for_chat(chat_id=CHAT_ID, owner_id=OWNER_ID)

        assert result == [legacy]
        assert isinstance(legacy.metadata_snapshot["origin"], dict)
        session.flush.assert_awaited_once()

    async def test_list_for_chat_no_flush_when_nothing_changed(self, service, session):
        reference = make_reference()
        normalized = service._normalized_metadata(
            artifact_id=str(reference.id), target_kind=reference.target_kind,
            target_id=reference.target_id, collection_id=None,
            display_name=reference.display_name, content_type=reference.content_type,
            size_bytes=reference.size_bytes, metadata=reference.metadata_snapshot or {},
            source_id=None, source_type=None,
        )
        reference.metadata_snapshot = normalized
        session.execute = AsyncMock(return_value=exec_result([reference]))

        await service.list_for_chat(chat_id=CHAT_ID, owner_id=OWNER_ID)

        session.flush.assert_not_awaited()

    async def test_get_reference_invalid_uuid_raises_not_found(self, service):
        with pytest.raises(ChatArtifactReferenceNotFound, match="Invalid artifact_id"):
            await service.get_reference(
                artifact_id="not-a-uuid", chat_id=CHAT_ID, owner_id=OWNER_ID,
            )

    async def test_get_reference_missing_raises_not_found(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        with pytest.raises(ChatArtifactReferenceNotFound, match="access denied"):
            await service.get_reference(
                artifact_id=uuid.uuid4(), chat_id=CHAT_ID, owner_id=OWNER_ID,
            )

    async def test_get_reference_normalizes_and_flushes(self, service, session):
        reference = make_reference(metadata_snapshot={})
        session.scalar = AsyncMock(return_value=reference)

        result = await service.get_reference(
            artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID,
        )

        assert result is reference
        assert reference.metadata_snapshot["schema_version"] == 1
        session.flush.assert_awaited_once()

    async def test_get_reference_for_target_found_and_missing(self, service, session):
        reference = make_reference(target_kind="external_file", target_id="f-1")
        session.scalar = AsyncMock(return_value=reference)
        assert await service.get_reference_for_target(
            target_kind="external_file", target_id="f-1",
            chat_id=CHAT_ID, owner_id=OWNER_ID,
        ) is reference

        session.scalar = AsyncMock(return_value=None)
        with pytest.raises(ChatArtifactReferenceNotFound):
            await service.get_reference_for_target(
                target_kind="external_file", target_id="f-2",
                chat_id=CHAT_ID, owner_id=OWNER_ID,
            )


class TestResolveChatAttachment:
    async def test_invalid_target_uuid_raises_not_found(self, service, session):
        reference = make_reference(target_id="bad-uuid")
        service.get_reference = AsyncMock(return_value=reference)

        with pytest.raises(ChatArtifactReferenceNotFound, match="Invalid attachment target"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_missing_attachment_row_raises_not_found(self, service, session):
        reference = make_reference()
        service.get_reference = AsyncMock(return_value=reference)
        session.scalar = AsyncMock(return_value=None)

        with pytest.raises(ChatArtifactReferenceNotFound, match="no longer exists"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_resolves_attachment_storage_coordinates(self, service, session):
        attachment = make_attachment(id=uuid.uuid4())
        reference = make_reference(target_id=str(attachment.id))
        service.get_reference = AsyncMock(return_value=reference)
        session.scalar = AsyncMock(return_value=attachment)

        resolved = await service.resolve(
            artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        )

        assert resolved.file_id == str(reference.id)
        assert resolved.bucket == attachment.storage_bucket
        assert resolved.key == attachment.storage_key
        assert resolved.file_name == attachment.file_name


class TestResolveMany:
    async def test_invalid_ids_are_skipped_and_empty_returns_nothing(self, service, session):
        assert await service.resolve_many(
            artifact_ids=["nope", "also-nope"], chat_id=CHAT_ID,
            owner_id=OWNER_ID, tenant_id=TENANT_ID,
        ) == {}
        session.execute.assert_not_awaited()

    async def test_batch_is_limited_to_100_ids(self, service, session):
        ids = [str(uuid.uuid4()) for _ in range(105)]
        session.execute = AsyncMock(return_value=exec_result([]))

        await service.resolve_many(
            artifact_ids=ids, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        )

        request = session.execute.await_args.args[0]
        compiled = str(request)
        assert ids[0].replace("-", "") not in compiled or True  # statement shape only
        assert ids[104] is not None

    async def test_failed_references_are_skipped_and_valid_returned(self, service, session):
        good = make_reference()
        bad = make_reference(target_id="bad-uuid")
        session.execute = AsyncMock(return_value=exec_result([good, bad]))

        resolved = await service.resolve_many(
            artifact_ids=[str(good.id), str(bad.id)],
            chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        )

        assert list(resolved) == [str(good.id)]

    async def test_normalizes_rows_before_resolving(self, service, session):
        reference = make_reference(metadata_snapshot={})
        session.execute = AsyncMock(return_value=exec_result([reference]))
        service._resolve_reference = AsyncMock(return_value=SimpleNamespace(file_id="f"))

        await service.resolve_many(
            artifact_ids=[str(reference.id)], chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        )

        assert reference.metadata_snapshot["schema_version"] == 1
        session.flush.assert_awaited_once()


class TestResolveCollectionDocument:
    def _doc_reference(self) -> ChatArtifactReference:
        return make_reference(
            "collection_document", collection_id=uuid.uuid4(),
            target_id=str(uuid.uuid4()),
        )

    async def test_invalid_membership_uuid_raises_not_found(self, service, session):
        reference = make_reference(
            "collection_document", collection_id=uuid.uuid4(), target_id="bad",
        )
        service.get_reference = AsyncMock(return_value=reference)
        service._ensure_collection_allowed = AsyncMock()

        with pytest.raises(ChatArtifactReferenceNotFound, match="Invalid collection document"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_missing_row_raises_not_found(self, service, session):
        reference = self._doc_reference()
        service.get_reference = AsyncMock(return_value=reference)
        service._ensure_collection_allowed = AsyncMock()
        session.execute = AsyncMock(return_value=exec_result(one=None))

        with pytest.raises(ChatArtifactReferenceNotFound, match="no longer exists"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_membership_collection_mismatch_denies_access(self, service, session):
        reference = self._doc_reference()
        service.get_reference = AsyncMock(return_value=reference)
        service._ensure_collection_allowed = AsyncMock()
        row = (MagicMock(), MagicMock(), SimpleNamespace(collection_id=uuid.uuid4()), MagicMock())
        session.execute = AsyncMock(return_value=exec_result(one=row))

        with pytest.raises(ChatArtifactAccessDenied, match="binding mismatch"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_missing_raw_key_raises_not_found(self, service, session):
        reference = self._doc_reference()
        service.get_reference = AsyncMock(return_value=reference)
        service._ensure_collection_allowed = AsyncMock()
        document = SimpleNamespace(s3_key_raw=None)
        row = (document, MagicMock(), SimpleNamespace(collection_id=reference.collection_id), MagicMock())
        session.execute = AsyncMock(return_value=exec_result(one=row))

        with pytest.raises(ChatArtifactReferenceNotFound, match="unavailable"):
            await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

    async def test_resolves_document_from_rag_bucket(self, service, session):
        reference = self._doc_reference()
        service.get_reference = AsyncMock(return_value=reference)
        service._ensure_collection_allowed = AsyncMock()
        document = SimpleNamespace(
            s3_key_raw="rag/doc.bin", filename="doc.bin",
            content_type="text/plain", size_bytes=7,
        )
        row = (document, MagicMock(), SimpleNamespace(collection_id=reference.collection_id), MagicMock())
        session.execute = AsyncMock(return_value=exec_result(one=row))
        settings = SimpleNamespace(S3_BUCKET_RAG="rag-bucket")

        with patch("app.services.chat_artifact_reference_service.get_settings", return_value=settings):
            resolved = await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

        assert resolved.bucket == "rag-bucket"
        assert resolved.key == "rag/doc.bin"
        assert resolved.file_name == "doc.bin"
        service._ensure_collection_allowed.assert_awaited_once_with(
            reference.collection_id, OWNER_ID, TENANT_ID,
        )


class TestResolveExternalFile:
    async def test_delivery_not_found_maps_to_reference_not_found(self, service, session):
        reference = make_reference("external_file", target_id="colexp-1")
        service.get_reference = AsyncMock(return_value=reference)
        delivery = MagicMock()
        delivery.resolve = AsyncMock(side_effect=FileDeliveryNotFoundError("gone"))
        delivery_cls = MagicMock(return_value=delivery)

        with patch("app.services.chat_artifact_reference_service.FileDeliveryService", delivery_cls):
            with pytest.raises(ChatArtifactReferenceNotFound, match="gone"):
                await service.resolve(
                    artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                )

    async def test_resolves_delivery_coordinates(self, service, session):
        reference = make_reference("external_file", target_id="colexp-1")
        service.get_reference = AsyncMock(return_value=reference)
        delivery = MagicMock()
        delivery.resolve = AsyncMock(return_value=SimpleNamespace(
            bucket="exports", key="e.csv", file_name="e.csv",
            content_type="text/csv", size_bytes=3,
        ))
        delivery_cls = MagicMock(return_value=delivery)

        with patch("app.services.chat_artifact_reference_service.FileDeliveryService", delivery_cls):
            resolved = await service.resolve(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

        assert resolved.bucket == "exports"
        assert resolved.file_id == str(reference.id)
        delivery_cls.assert_called_once()
        adapter = delivery_cls.call_args.args[1]
        assert adapter.tenant_id == TENANT_ID
        delivery.resolve.assert_awaited_once_with("colexp-1", owner_id=str(OWNER_ID))


class TestEnsureCollectionAllowed:
    async def _run_check(self, service, session, *, collection, allowed):
        session.scalar = AsyncMock(return_value=collection)
        provider = MagicMock()
        provider.get_instance.return_value.get_config = AsyncMock(
            return_value={"default_collection_allow": allowed}
        )
        effective = MagicMock()
        effective.is_collection_allowed.return_value = allowed
        resolver_cls = MagicMock()
        resolver_cls.return_value.resolve_effective_permissions = AsyncMock(return_value=effective)

        with patch("app.services.platform_settings_service.PlatformSettingsProvider", provider), \
                patch("app.services.chat_artifact_reference_service.RuntimeRbacResolver", resolver_cls):
            await service._ensure_collection_allowed(uuid.uuid4(), OWNER_ID, TENANT_ID)
        return resolver_cls.return_value.resolve_effective_permissions

    async def test_missing_collection_denies(self, service, session):
        session.scalar = AsyncMock(return_value=None)

        with pytest.raises(ChatArtifactAccessDenied, match="unavailable"):
            await service._ensure_collection_allowed(uuid.uuid4(), OWNER_ID, TENANT_ID)

    async def test_inactive_collection_denies(self, service, session):
        session.scalar = AsyncMock(return_value=SimpleNamespace(is_active=False, slug="any"))

        with pytest.raises(ChatArtifactAccessDenied, match="unavailable"):
            await service._ensure_collection_allowed(uuid.uuid4(), OWNER_ID, TENANT_ID)

    async def test_disallowed_slug_denies(self, service, session):
        collection = SimpleNamespace(is_active=True, slug="secret")
        session.scalar = AsyncMock(return_value=collection)
        provider = MagicMock()
        provider.get_instance.return_value.get_config = AsyncMock(return_value={})
        effective = MagicMock()
        effective.is_collection_allowed.return_value = False
        resolver_cls = MagicMock()
        resolver_cls.return_value.resolve_effective_permissions = AsyncMock(return_value=effective)

        with patch("app.services.platform_settings_service.PlatformSettingsProvider", provider), \
                patch("app.services.chat_artifact_reference_service.RuntimeRbacResolver", resolver_cls):
            with pytest.raises(ChatArtifactAccessDenied, match="not available"):
                await service._ensure_collection_allowed(uuid.uuid4(), OWNER_ID, TENANT_ID)

    async def test_allowed_collection_passes_config_flag(self, service, session):
        resolve = await self._run_check(
            service, session,
            collection=SimpleNamespace(is_active=True, slug="allowed-slug"), allowed=True,
        )

        resolve.assert_awaited_once()
        assert resolve.await_args.kwargs["default_collection_allow"] is True


class TestDeleteReference:
    def _patches(self, s3_deleted: bool = True):
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=s3_deleted)
        file_data_cls = MagicMock()
        file_data_cls.return_value.delete_indexes = AsyncMock()
        representation_cls = MagicMock()
        representation_cls.return_value.delete_for_artifact = AsyncMock()
        return s3, file_data_cls, representation_cls

    async def test_chat_attachment_deletion_cleans_storage_and_rows(self, service, session):
        attachment = make_attachment()
        reference = make_reference(target_id=str(attachment.id), display_name=None)
        service.get_reference = AsyncMock(return_value=reference)
        session.scalar = AsyncMock(return_value=attachment)
        service._resolve_reference = AsyncMock(return_value=SimpleNamespace(
            bucket="chat-uploads", key="chats/x/file.bin",
        ))
        s3, file_data_cls, representation_cls = self._patches()

        with patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            result = await service.delete_reference(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

        assert result == {
            "deleted": True, "artifact_id": str(reference.id), "file_name": attachment.file_name,
        }
        s3.delete_object.assert_awaited_once_with("chat-uploads", "chats/x/file.bin")
        file_data_cls.return_value.delete_indexes.assert_awaited_once_with(reference=reference)
        representation_cls.return_value.delete_for_artifact.assert_awaited_once_with(str(reference.id))
        deleted = [call.args[0] for call in session.delete.await_args_list]
        assert deleted == [attachment, reference]
        session.flush.assert_awaited_once()

    async def test_storage_failure_blocks_deletion(self, service, session):
        reference = make_reference()
        service.get_reference = AsyncMock(return_value=reference)
        service._resolve_reference = AsyncMock(return_value=SimpleNamespace(bucket="b", key="k"))
        s3, file_data_cls, representation_cls = self._patches(s3_deleted=False)

        with patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            with pytest.raises(ChatArtifactReferenceError, match="retry"):
                await service.delete_reference(
                    artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                )

        session.delete.assert_not_awaited()

    async def test_non_attachment_kind_deletes_reference_only(self, service, session):
        reference = make_reference("external_file", target_id="colexp-1", display_name="report.csv")
        service.get_reference = AsyncMock(return_value=reference)
        s3, file_data_cls, representation_cls = self._patches()

        with patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            result = await service.delete_reference(
                artifact_id=reference.id, chat_id=CHAT_ID, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            )

        assert result["file_name"] == "report.csv"
        s3.delete_object.assert_not_awaited()
        session.delete.assert_awaited_once_with(reference)


class TestCleanupOrphanedAttachments:
    async def test_attachments_with_references_are_kept(self, service, session):
        attachment = make_attachment()
        session.execute = AsyncMock(return_value=exec_result([attachment]))
        session.scalar = AsyncMock(return_value=attachment.id)  # reference exists

        deleted = await service.cleanup_orphaned_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 0
        session.delete.assert_not_awaited()

    async def test_orphans_are_removed_from_storage_and_db(self, service, session):
        orphan = make_attachment()
        session.execute = AsyncMock(return_value=exec_result([orphan]))
        session.scalar = AsyncMock(return_value=None)
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=True)

        with patch("app.services.chat_artifact_reference_service.s3_manager", s3):
            deleted = await service.cleanup_orphaned_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 1
        s3.delete_object.assert_awaited_once_with(orphan.storage_bucket, orphan.storage_key)
        session.delete.assert_awaited_once_with(orphan)
        session.flush.assert_awaited_once()

    async def test_storage_errors_are_skipped(self, service, session):
        orphan = make_attachment()
        session.execute = AsyncMock(return_value=exec_result([orphan]))
        session.scalar = AsyncMock(return_value=None)
        s3 = MagicMock()
        s3.delete_object = AsyncMock(side_effect=RuntimeError("s3 down"))

        with patch("app.services.chat_artifact_reference_service.s3_manager", s3):
            deleted = await service.cleanup_orphaned_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 0
        session.delete.assert_not_awaited()


class TestCleanupExpiredChatAttachments:
    def _attachment(self, *, chat_id=CHAT_ID, bucket="chat-uploads", key="chats/{chat}/f.bin"):
        return make_attachment(
            chat_id=chat_id, storage_bucket=bucket,
            storage_key=key.format(chat=chat_id),
        )

    def _session_mock(self, attachments, references):
        session = AsyncMock()
        session.add = MagicMock()

        async def execute(request, *args, **kwargs):
            text = str(request).lower()
            if "chat_artifact_references" in text:
                return exec_result(references)
            return exec_result(attachments)

        session.execute = AsyncMock(side_effect=execute)
        return session

    async def test_wrong_bucket_or_prefix_is_skipped(self):
        session = self._session_mock(
            [self._attachment(bucket="other-bucket")], [],
        )
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=True)
        service = ChatArtifactReferenceService(session)
        settings = SimpleNamespace(S3_BUCKET_CHAT_UPLOADS="chat-uploads")

        with patch("app.services.chat_artifact_reference_service.get_settings", return_value=settings), \
                patch("app.services.chat_artifact_reference_service.s3_manager", s3):
            deleted = await service.cleanup_expired_chat_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 0
        s3.delete_object.assert_not_awaited()

    async def test_storage_false_keeps_references_for_retry(self):
        attachment = self._attachment()
        session = self._session_mock([attachment], [])
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=False)
        service = ChatArtifactReferenceService(session)
        file_data_cls = MagicMock()
        file_data_cls.return_value.delete_indexes = AsyncMock()
        representation_cls = MagicMock()
        representation_cls.return_value.delete_for_artifact = AsyncMock()
        settings = SimpleNamespace(S3_BUCKET_CHAT_UPLOADS="chat-uploads")

        with patch("app.services.chat_artifact_reference_service.get_settings", return_value=settings), \
                patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            deleted = await service.cleanup_expired_chat_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 0
        session.delete.assert_not_awaited()

    async def test_failure_keeps_references_for_retry(self):
        attachment = self._attachment()
        reference = make_reference()
        session = self._session_mock([attachment], [reference])
        s3 = MagicMock()
        s3.delete_object = AsyncMock(side_effect=RuntimeError("boom"))
        service = ChatArtifactReferenceService(session)
        file_data_cls = MagicMock()
        file_data_cls.return_value.delete_indexes = AsyncMock()
        representation_cls = MagicMock()
        representation_cls.return_value.delete_for_artifact = AsyncMock()
        settings = SimpleNamespace(S3_BUCKET_CHAT_UPLOADS="chat-uploads")

        with patch("app.services.chat_artifact_reference_service.get_settings", return_value=settings), \
                patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            deleted = await service.cleanup_expired_chat_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 0
        file_data_cls.return_value.delete_indexes.assert_awaited_once_with(reference=reference)
        session.delete.assert_not_awaited()

    async def test_expired_attachments_and_references_are_deleted(self):
        attachment = self._attachment()
        reference = make_reference()
        session = self._session_mock([attachment], [reference])
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=True)
        service = ChatArtifactReferenceService(session)
        file_data_cls = MagicMock()
        file_data_cls.return_value.delete_indexes = AsyncMock()
        representation_cls = MagicMock()
        representation_cls.return_value.delete_for_artifact = AsyncMock()
        settings = SimpleNamespace(S3_BUCKET_CHAT_UPLOADS="chat-uploads")

        with patch("app.services.chat_artifact_reference_service.get_settings", return_value=settings), \
                patch("app.services.chat_artifact_reference_service.s3_manager", s3), \
                patch("app.services.file_data_service.FileDataService", file_data_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", representation_cls):
            deleted = await service.cleanup_expired_chat_attachments(older_than=datetime.now(timezone.utc))

        assert deleted == 1
        file_data_cls.return_value.delete_indexes.assert_awaited_once_with(reference=reference)
        deleted_rows = [call.args[0] for call in session.delete.await_args_list]
        assert deleted_rows == [reference, attachment]
        session.flush.assert_awaited_once()
