"""Extended unit tests for ChatAttachmentService.

Covers upload policy resolution from platform settings, upload happy path
and storage failures, generated-attachment lifecycle incl. rollback paths,
ownership resolution and message binding, artifact metadata projection,
runtime attachment contexts, and detached-attachment cleanup.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.exceptions import ChatAttachmentNotFoundError
from app.services.chat_attachment_service import (
    DEFAULT_CHAT_UPLOAD_ALLOWED_EXTENSIONS,
    DEFAULT_CHAT_UPLOAD_MAX_BYTES,
    ChatAttachmentService,
)
from app.services.chat_artifact_reference_service import ChatArtifactReferenceNotFound

CHAT_ID = uuid.uuid4()
OWNER_ID = uuid.uuid4()


def exec_result(rows: list = (), scalar=None, rowcount: int | None = None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalar_one_or_none.return_value = scalar
    result.rowcount = rowcount
    return result


def make_reference(**overrides) -> SimpleNamespace:
    payload = {
        "id": uuid.uuid4(),
        "display_name": "notes.txt",
        "content_type": "text/plain",
        "size_bytes": 42,
        "metadata_snapshot": {"status": "uploaded"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def make_row(**overrides) -> SimpleNamespace:
    payload = {
        "id": uuid.uuid4(),
        "chat_id": CHAT_ID,
        "owner_id": OWNER_ID,
        "file_name": "notes.txt",
        "storage_bucket": "chat-uploads",
        "storage_key": "chats/x/notes.txt",
        "message_id": None,
        "linked_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def reference_service_mock(reference: SimpleNamespace | None = None, manifest: dict | None = None):
    refs_cls = MagicMock()
    refs_cls.return_value.get_reference = AsyncMock(return_value=reference)
    refs_cls.return_value.register = AsyncMock(return_value=reference)
    refs_cls.return_value.manifest = MagicMock(
        return_value=manifest if manifest is not None else {
            "origin": {"kind": "user_upload", "source_id": "s"},
            "description": None,
            "attributes": {},
        },
    )
    refs_cls.manifest = refs_cls.return_value.manifest
    return refs_cls


@pytest.fixture
def session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service(session) -> ChatAttachmentService:
    return ChatAttachmentService(session)


class TestGetUploadPolicy:
    async def test_missing_settings_row_yields_defaults(self, service, session):
        session.execute = AsyncMock(return_value=exec_result(scalar=None))

        policy = await service.get_upload_policy()

        assert policy.max_bytes == DEFAULT_CHAT_UPLOAD_MAX_BYTES
        assert sorted(policy.allowed_extensions) == sorted(
            ext.strip() for ext in DEFAULT_CHAT_UPLOAD_ALLOWED_EXTENSIONS.split(",")
        )
        assert "txt" in policy.allowed_content_types_by_extension

    async def test_row_values_override_defaults_and_csv_is_normalized(self, service, session):
        row = SimpleNamespace(chat_upload_max_bytes=123, chat_upload_allowed_extensions=" .TXT , pdf ,, ")
        session.execute = AsyncMock(return_value=exec_result(scalar=row))

        policy = await service.get_upload_policy()

        assert policy.max_bytes == 123
        assert policy.allowed_extensions == ["txt", "pdf"]
        assert set(policy.allowed_content_types_by_extension) == {"txt", "pdf"}

    async def test_falsy_row_fields_and_empty_csv_fall_back(self, service, session):
        row = SimpleNamespace(chat_upload_max_bytes=0, chat_upload_allowed_extensions=",,,")
        session.execute = AsyncMock(return_value=exec_result(scalar=row))

        policy = await service.get_upload_policy()

        assert policy.max_bytes == DEFAULT_CHAT_UPLOAD_MAX_BYTES
        assert sorted(policy.allowed_extensions) == sorted(
            {"txt", "md", "pdf", "doc", "docx", "xls", "xlsx", "csv"}
        )


class TestUploadAttachment:
    def _file(self, content: bytes = b"hello world"):
        return SimpleNamespace(
            filename="notes.txt", content_type="text/plain",
            read=AsyncMock(return_value=content),
        )

    def _s3(self, uploaded: bool = True):
        s3 = MagicMock()
        s3.upload_fileobj = AsyncMock(return_value=uploaded)
        s3.delete_object = AsyncMock(return_value=True)
        s3._get_client.return_value.head_bucket.return_value = {}
        return s3

    async def test_happy_path_uploads_storage_and_registers_reference(self, service, session):
        service.get_upload_policy = AsyncMock(return_value=SimpleNamespace(
            max_bytes=1000, allowed_extensions=["txt"],
        ))
        reference = make_reference()
        refs_cls = reference_service_mock(reference)
        file = self._file()
        s3 = self._s3()

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk123"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            result = await service.upload_attachment(
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID), file=file,
            )

        assert result["artifact_id"] == str(reference.id)
        assert result["file_name"] == "notes.txt"
        assert result["file_ext"] == "txt"
        assert result["status"] == "uploaded"
        assert result["origin"] == {"kind": "user_upload", "source_id": "s"}

        file.read.assert_awaited_once_with(1001)
        bucket = service.settings.S3_BUCKET_CHAT_UPLOADS
        upload = s3.upload_fileobj.await_args
        assert upload.kwargs["bucket"] == bucket
        assert upload.kwargs["key"].startswith(f"chats/{CHAT_ID}/attachments/")
        assert upload.kwargs["key"].endswith("/chk123_notes.txt")
        assert upload.kwargs["metadata"] == {
            "chat_id": str(CHAT_ID), "owner_id": str(OWNER_ID), "checksum": "chk123",
        }
        session.add.assert_called_once()
        target = refs_cls.return_value.register.await_args.kwargs["target"]
        assert target.kind == "chat_attachment"
        assert target.source_type == "chat_upload"
        assert target.display_name == "notes.txt"

    async def test_failed_storage_upload_raises_without_registration(self, service, session):
        service.get_upload_policy = AsyncMock(return_value=SimpleNamespace(
            max_bytes=1000, allowed_extensions=["txt"],
        ))
        refs_cls = reference_service_mock(make_reference())
        s3 = self._s3(uploaded=False)

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(RuntimeError, match="Failed to upload file"):
                await service.upload_attachment(
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID), file=self._file(),
                )

        refs_cls.return_value.register.assert_not_awaited()
        session.add.assert_not_called()


class TestCreateGeneratedAttachment:
    def _s3(self, uploaded: bool = True):
        s3 = MagicMock()
        s3.upload_fileobj = AsyncMock(return_value=uploaded)
        s3.delete_object = AsyncMock(return_value=True)
        s3._get_client.return_value.head_bucket.return_value = {}
        return s3

    async def test_generated_file_is_registered_with_supplied_metadata(self, service, session):
        reference = make_reference(status=None, metadata_snapshot={"status": "generated"})
        refs_cls = reference_service_mock(reference)
        s3 = self._s3()

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="genchk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            result = await service.create_generated_attachment(
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                filename="../../report v2.csv", content=b"a,b,c",
                content_type="text/csv", metadata={"root_run_id": "run-1"},
            )

        assert result["artifact_id"] == str(reference.id)
        upload = s3.upload_fileobj.await_args
        assert upload.kwargs["key"].startswith(f"chats/{CHAT_ID}/generated/")
        assert upload.kwargs["key"].endswith("/genchk_report v2.csv")
        assert upload.kwargs["metadata"] == {
            "owner_id": str(OWNER_ID), "checksum": "genchk",
            "generated": "true", "chat_id": str(CHAT_ID),
        }
        target = refs_cls.return_value.register.await_args.kwargs["target"]
        assert target.metadata == {"status": "generated", "root_run_id": "run-1"}
        assert target.source_type == "generated_attachment"
        assert session.add.call_count == 1

    async def test_missing_chat_scopes_are_rolled_back(self, service, session):
        refs_cls = reference_service_mock(make_reference())
        s3 = self._s3()

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(RuntimeError, match="chat-scoped artifact reference"):
                await service.create_generated_attachment(
                    chat_id=None, owner_id=str(OWNER_ID),
                    filename="free.bin", content=b"data",
                )

        refs_cls.return_value.register.assert_not_awaited()
        session.delete.assert_awaited_once()
        upload_key = s3.upload_fileobj.await_args.kwargs["key"]
        s3.delete_object.assert_awaited_once_with(service.settings.S3_BUCKET_CHAT_UPLOADS, upload_key)

    async def test_failed_upload_raises_before_row_creation(self, service, session):
        refs_cls = reference_service_mock(make_reference())
        s3 = self._s3(uploaded=False)

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(RuntimeError, match="Failed to upload generated file"):
                await service.create_generated_attachment(
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                    filename="x.txt", content=b"data",
                )

        session.add.assert_not_called()
        s3.delete_object.assert_not_awaited()

    async def test_registration_failure_rolls_back_row_and_object(self, service, session):
        refs_cls = reference_service_mock(make_reference())
        refs_cls.return_value.register = AsyncMock(side_effect=RuntimeError("register boom"))
        s3 = self._s3()

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(RuntimeError, match="register boom"):
                await service.create_generated_attachment(
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                    filename="x.txt", content=b"data",
                )

        session.delete.assert_awaited_once()
        upload_key = s3.upload_fileobj.await_args.kwargs["key"]
        s3.delete_object.assert_awaited_once_with(service.settings.S3_BUCKET_CHAT_UPLOADS, upload_key)

    async def test_rollback_failures_are_swallowed_and_original_raised(self, service, session):
        refs_cls = reference_service_mock(make_reference())
        refs_cls.return_value.register = AsyncMock(side_effect=RuntimeError("register boom"))
        s3 = self._s3()
        s3.delete_object = AsyncMock(side_effect=RuntimeError("s3 rollback boom"))
        session.delete = AsyncMock(side_effect=RuntimeError("db rollback boom"))

        with patch("app.services.chat_attachment_service.s3_manager", s3), \
                patch("app.services.chat_attachment_service.calculate_file_checksum", return_value="chk"), \
                patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(RuntimeError, match="register boom"):
                await service.create_generated_attachment(
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                    filename="x.txt", content=b"data",
                )

        session.delete.assert_awaited_once()
        s3.delete_object.assert_awaited_once()


class TestGetOwnedAttachments:
    async def test_invalid_id_raises_not_found(self, service):
        with pytest.raises(ChatAttachmentNotFoundError, match="Invalid attachment id"):
            await service.get_owned_attachments(
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID), attachment_ids=["nope"],
            )

    async def test_empty_input_returns_without_query(self, service, session):
        result = await service.get_owned_attachments(
            chat_id=str(CHAT_ID), owner_id=str(OWNER_ID), attachment_ids=[],
        )

        assert result == []
        session.execute.assert_not_awaited()

    async def test_row_count_mismatch_raises_not_found(self, service, session):
        session.execute = AsyncMock(return_value=exec_result([make_row()]))

        with pytest.raises(ChatAttachmentNotFoundError, match="not found or not accessible"):
            await service.get_owned_attachments(
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                attachment_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            )

    async def test_owned_rows_are_returned(self, service, session):
        rows = [make_row(), make_row()]
        session.execute = AsyncMock(return_value=exec_result(rows))

        result = await service.get_owned_attachments(
            chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            attachment_ids=[str(row.id) for row in rows],
        )

        assert result == rows


class TestBindToMessage:
    async def test_only_unbound_rows_are_linked_and_flushed(self, service, session):
        bound = make_row(message_id=uuid.uuid4())
        unbound = make_row()
        service.get_owned_attachments = AsyncMock(return_value=[bound, unbound])
        message_id = uuid.uuid4()

        result = await service.bind_to_message(
            chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            attachment_ids=[str(bound.id), str(unbound.id)], message_id=str(message_id),
        )

        assert result == [bound, unbound]
        assert bound.message_id != message_id
        assert unbound.message_id == message_id
        assert unbound.linked_at is not None
        assert bound.linked_at is None
        session.flush.assert_awaited_once()


class TestBindArtifactsToMessage:
    async def test_only_chat_attachment_targets_are_bound(self, service):
        attachment_ref = SimpleNamespace(target_kind="chat_attachment", target_id="att-1")
        external_ref = SimpleNamespace(target_kind="external_file", target_id="colexp-1")
        refs_cls = reference_service_mock()
        refs_cls.return_value.get_reference = AsyncMock(
            side_effect=[attachment_ref, external_ref],
        )
        rows = [make_row()]
        message_id = str(uuid.uuid4())
        service.bind_to_message = AsyncMock(return_value=rows)

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            result = await service.bind_artifacts_to_message(
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                artifact_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
                message_id=message_id,
            )

        assert result is rows
        service.bind_to_message.assert_awaited_once_with(
            chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            attachment_ids=["att-1"], message_id=message_id,
        )


class TestArtifactMetadata:
    async def test_missing_reference_maps_to_attachment_not_found(self, service):
        refs_cls = reference_service_mock()
        refs_cls.return_value.get_reference = AsyncMock(
            side_effect=ChatArtifactReferenceNotFound("gone"),
        )

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            with pytest.raises(ChatAttachmentNotFoundError, match="gone"):
                await service.artifact_metadata(
                    artifact_ids=[str(uuid.uuid4())],
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                )

    async def test_manifest_is_extended_with_flat_file_fields(self, service):
        reference = make_reference(
            display_name="data.tar.gz", content_type=None, size_bytes=None,
            metadata_snapshot={},
        )
        refs_cls = reference_service_mock(reference, manifest={
            "origin": {"kind": "external_file", "source_id": "s"},
            "description": None, "attributes": {"custom": 1},
        })

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls):
            result = await service.artifact_metadata(
                artifact_ids=[str(reference.id)],
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            )

        assert result == [{
            "origin": {"kind": "external_file", "source_id": "s"},
            "description": None, "attributes": {"custom": 1},
            "artifact_id": str(reference.id),
            "file_name": "data.tar.gz",
            "file_ext": "gz",
            "content_type": None,
            "size_bytes": None,
            "status": "ready",
        }]


class TestBuildRuntimeArtifactContexts:
    def _patches(self, reference, representation, manifest=None):
        refs_cls = reference_service_mock(reference, manifest=manifest)
        rep_cls = MagicMock()
        rep_cls.return_value.metadata = AsyncMock(return_value=representation)
        return refs_cls, rep_cls

    async def test_blank_and_duplicate_ids_are_skipped(self, service):
        reference = make_reference()
        refs_cls, rep_cls = self._patches(reference, {"status": "ready", "id": "rep-1"})

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", rep_cls):
            contexts = await service.build_runtime_artifact_contexts(
                artifact_ids=["", "   ", str(reference.id), str(reference.id)],
                chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            )

        assert len(contexts) == 1
        assert contexts[0].ref.artifact_id == str(reference.id)
        refs_cls.return_value.get_reference.assert_awaited_once()

    async def test_missing_reference_raises_attachment_not_found(self, service):
        refs_cls, rep_cls = self._patches(make_reference(), {})
        refs_cls.return_value.get_reference = AsyncMock(
            side_effect=ChatArtifactReferenceNotFound("gone"),
        )

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", rep_cls):
            with pytest.raises(ChatAttachmentNotFoundError, match="gone"):
                await service.build_runtime_artifact_contexts(
                    artifact_ids=[str(uuid.uuid4())],
                    chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                )

    async def test_ready_representation_marks_source_complete(self, service):
        reference = make_reference()
        refs_cls, rep_cls = self._patches(
            reference, {"status": "ready", "id": "rep-9"},
            manifest={
                "origin": {"kind": "user_upload", "source_id": "s"},
                "description": {"text": "Quarterly notes"},
                "attributes": {"file_data": {"rag": {"status": "ready"}}},
            },
        )

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", rep_cls):
            contexts = await service.build_runtime_artifact_contexts(
                artifact_ids=[str(reference.id)], chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
                current_artifact_ids=[str(reference.id), str(uuid.uuid4())],
            )

        context = contexts[0]
        assert context.is_current is True
        assert context.representation_id == "rep-9"
        assert context.source_complete is True
        assert context.readable is True
        assert context.truncated is False
        assert context.snippet == ""
        assert context.snippet_status == "ready"
        assert context.ref.description == "Quarterly notes"
        assert context.ref.data_indexes == {"rag": {"status": "ready"}}
        rep_cls.return_value.metadata.assert_awaited_once_with(str(reference.id))

    async def test_partial_representation_is_readable_but_truncated(self, service):
        reference = make_reference()
        refs_cls, rep_cls = self._patches(reference, {"status": "partial", "id": "rep-2"})

        with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", refs_cls), \
                patch("app.services.artifact_representation_service.ArtifactRepresentationService", rep_cls):
            contexts = await service.build_runtime_artifact_contexts(
                artifact_ids=[str(reference.id)], chat_id=str(CHAT_ID), owner_id=str(OWNER_ID),
            )

        context = contexts[0]
        assert context.is_current is False
        assert context.source_complete is False
        assert context.readable is True
        assert context.truncated is True
        assert context.snippet_status == "partial"


class TestCleanupExpiredDetachedAttachments:
    async def test_deletes_storage_objects_then_rows(self, service, session):
        rows = [make_row(chat_id=None), make_row(chat_id=None)]
        session.execute = AsyncMock(return_value=exec_result(rows, rowcount=2))
        s3 = MagicMock()
        s3.delete_object = AsyncMock(return_value=True)

        cutoff = datetime.now(timezone.utc)
        with patch("app.services.chat_attachment_service.s3_manager", s3):
            deleted = await service.cleanup_expired_detached_attachments(older_than=cutoff)

        assert deleted == 2
        assert s3.delete_object.await_count == 2
        session.flush.assert_awaited_once()

    async def test_storage_failures_do_not_block_row_deletion(self, service, session):
        rows = [make_row(chat_id=None)]
        session.execute = AsyncMock(return_value=exec_result(rows, rowcount=1))
        s3 = MagicMock()
        s3.delete_object = AsyncMock(side_effect=RuntimeError("s3 down"))

        with patch("app.services.chat_attachment_service.s3_manager", s3):
            deleted = await service.cleanup_expired_detached_attachments(
                older_than=datetime.now(timezone.utc),
            )

        assert deleted == 1
        session.flush.assert_awaited_once()


class TestHelpers:
    def test_sanitize_filename_strips_paths_and_slashes(self):
        # posix basename(): "/"-components are stripped, backslashes survive
        # basename and are neutralized by the explicit replace.
        assert ChatAttachmentService._sanitize_filename("a/b.txt") == "b.txt"
        assert ChatAttachmentService._sanitize_filename("..\\dir\\name.txt") == ".._dir_name.txt"
        assert ChatAttachmentService._sanitize_filename("   ") == "file"

    def test_extension_extraction(self):
        assert ChatAttachmentService._extension("archive.tar.gz") == "gz"
        assert ChatAttachmentService._extension("README") is None
        assert ChatAttachmentService._extension(None) is None

    async def test_ensure_bucket_creates_missing_bucket(self, service):
        client = MagicMock()
        client.head_bucket.side_effect = ClientError({"Error": {}}, "HeadBucket")
        s3 = MagicMock()
        s3._get_client.return_value = client

        with patch("app.services.chat_attachment_service.s3_manager", s3):
            await service._ensure_bucket("chat-uploads")

        client.create_bucket.assert_called_once_with(Bucket="chat-uploads")

    async def test_ensure_bucket_swallows_creation_failure(self, service):
        client = MagicMock()
        client.head_bucket.side_effect = ClientError({"Error": {}}, "HeadBucket")
        client.create_bucket.side_effect = RuntimeError("denied")
        s3 = MagicMock()
        s3._get_client.return_value = client

        with patch("app.services.chat_attachment_service.s3_manager", s3):
            await service._ensure_bucket("chat-uploads")

        client.create_bucket.assert_called_once_with(Bucket="chat-uploads")
