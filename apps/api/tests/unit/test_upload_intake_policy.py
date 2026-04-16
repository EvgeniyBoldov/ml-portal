from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.collection_document_ingest_service import CollectionDocumentUploadService
from app.services.rag_upload_service import RAGUploadService
from app.services.upload_intake_policy import UploadIntakePolicy, UploadValidationError


def test_upload_intake_policy_rejects_unknown_document_extension():
    with pytest.raises(UploadValidationError, match="Unsupported file extension"):
        UploadIntakePolicy.validate_document_upload(
            filename="payload.exe",
            content_type="application/octet-stream",
            size_bytes=10,
        )


def test_upload_intake_policy_rejects_mismatched_content_type():
    with pytest.raises(UploadValidationError, match="does not match '.pdf'"):
        UploadIntakePolicy.validate_document_upload(
            filename="report.pdf",
            content_type="text/plain",
            size_bytes=10,
        )


def test_upload_intake_policy_requires_csv_extension_for_csv_upload():
    with pytest.raises(UploadValidationError, match="requires a .csv file"):
        UploadIntakePolicy.validate_csv_upload(
            filename="report.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=10,
        )


@pytest.mark.asyncio
async def test_rag_upload_service_rejects_invalid_upload_before_s3(monkeypatch):
    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()
    service = RAGUploadService(
        session=MagicMock(),
        repo_factory=repo_factory,
        event_publisher=None,
    )
    upload_to_s3 = AsyncMock()
    monkeypatch.setattr(service, "_upload_to_s3", upload_to_s3)

    with pytest.raises(UploadValidationError, match="Unsupported file extension"):
        await service.upload_document(
            file_content=b"hello",
            filename="payload.exe",
            content_type="application/octet-stream",
            user_id=uuid4(),
        )

    upload_to_s3.assert_not_called()


@pytest.mark.asyncio
async def test_collection_upload_service_rejects_invalid_upload_before_s3(monkeypatch):
    repo_factory = MagicMock()
    repo_factory.tenant_id = uuid4()
    service = CollectionDocumentUploadService(
        session=MagicMock(),
        repo_factory=repo_factory,
        event_publisher=None,
    )
    collection = SimpleNamespace(
        id=uuid4(),
        qdrant_collection_name="coll_test_docs",
        row_count=0,
        total_rows=0,
        table_name="coll_test_docs",
        fields=[],
    )

    monkeypatch.setattr(service, "_get_document_collection", AsyncMock(return_value=collection))
    upload_to_s3 = AsyncMock()
    monkeypatch.setattr(service, "_upload_to_s3", upload_to_s3)

    with pytest.raises(UploadValidationError, match="Unsupported file extension"):
        await service.upload_document(
            collection_id=collection.id,
            file_content=b"hello",
            filename="payload.exe",
            content_type="application/octet-stream",
            user_id=uuid4(),
        )

    upload_to_s3.assert_not_called()


def test_chat_upload_policy_accepts_allowed_extension_and_size():
    descriptor = UploadIntakePolicy.validate_chat_upload(
        filename="notes.md",
        content_type="text/markdown",
        size_bytes=2048,
        max_bytes=10_000,
        allowed_extensions=["md", "txt"],
    )

    assert descriptor.extension == "md"
    assert descriptor.size_bytes == 2048


def test_chat_upload_policy_rejects_executable_extension():
    with pytest.raises(UploadValidationError, match="Executable files are not allowed"):
        UploadIntakePolicy.validate_chat_upload(
            filename="run.sh",
            content_type="text/plain",
            size_bytes=512,
            max_bytes=10_000,
            allowed_extensions=["sh", "txt"],
        )


def test_chat_upload_policy_rejects_executable_content_type():
    with pytest.raises(UploadValidationError, match="Executable content type is not allowed"):
        UploadIntakePolicy.validate_chat_upload(
            filename="report.txt",
            content_type="application/x-sh",
            size_bytes=512,
            max_bytes=10_000,
            allowed_extensions=["txt"],
        )


def test_chat_upload_policy_rejects_mismatched_content_type():
    with pytest.raises(UploadValidationError, match="does not match '.pdf'"):
        UploadIntakePolicy.validate_chat_upload(
            filename="report.pdf",
            content_type="text/plain",
            size_bytes=512,
            max_bytes=10_000,
            allowed_extensions=["pdf"],
        )


def test_chat_upload_policy_builds_content_type_map():
    mapping = UploadIntakePolicy.chat_allowed_content_types_by_extension(
        ["pdf", "txt", "unknown"]
    )
    assert "pdf" in mapping
    assert "txt" in mapping
    assert "unknown" not in mapping
