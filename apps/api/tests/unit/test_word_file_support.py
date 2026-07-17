from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.file_generate import FileGenerateTool
from app.agents.builtins.file_read import FileReadTool
from app.agents.context import ToolContext
from app.services.document_text_reader import read_text_from_bytes


def _make_docx_bytes(*paragraphs: str) -> bytes:
    pytest.importorskip("docx")
    from docx import Document  # type: ignore

    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_document_text_reader_extracts_docx_payload():
    data = _make_docx_bytes("Hello", "World")
    result = read_text_from_bytes(data, "example.docx")

    assert result is not None
    assert result.text == "Hello\nWorld"
    assert result.kind == "docx"


def test_document_text_reader_handles_mislabeled_docx_as_doc():
    data = _make_docx_bytes("Connectivity request")
    result = read_text_from_bytes(data, "example.doc")

    assert result is not None
    assert "Connectivity request" in result.text
    assert result.kind == "docx"


@pytest.mark.asyncio
async def test_file_read_returns_text_for_docx(monkeypatch):
    data = _make_docx_bytes("First paragraph", "Second paragraph")

    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    resolved = SimpleNamespace(
        bucket="bucket",
        key="path/example.docx",
        file_id="file-1",
        file_name="example.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    monkeypatch.setattr("app.core.db.get_session_factory", lambda: _SessionManager)
    monkeypatch.setattr(
        "app.repositories.factory.AsyncRepositoryFactory",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "app.services.file_delivery_service.FileDeliveryService.resolve_storage_uri",
        AsyncMock(return_value=resolved),
    )
    monkeypatch.setattr(
        "app.services.chat_artifact_reference_service.ChatArtifactReferenceService.resolve",
        AsyncMock(return_value=resolved),
    )
    monkeypatch.setattr("app.adapters.s3_client.s3_manager.get_object", AsyncMock(return_value=data))

    tool = FileReadTool()
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
    )

    result = await tool.v1_0_0(ctx, {"artifact_id": str(uuid4())})

    assert result.success is True
    assert result.data["representation"] == "document"
    assert "First paragraph" in result.data["content"]
    assert "Second paragraph" in result.data["content"]


@pytest.mark.asyncio
async def test_file_generate_supports_docx(monkeypatch):
    pytest.importorskip("docx")

    session = AsyncMock()

    class _SessionManager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    attachment_payload = {
        "id": str(uuid4()),
        "file_id": f"chatatt_{uuid4()}",
        "storage_uri": "s3://chat-bucket/chats/example/generated/report.docx",
        "file_name": "report.docx",
        "size_bytes": 5,
    }
    create_generated_attachment = AsyncMock(return_value=attachment_payload)
    service_instance = SimpleNamespace(create_generated_attachment=create_generated_attachment)

    monkeypatch.setattr("app.core.db.get_session_factory", lambda: _SessionManager)
    monkeypatch.setattr(
        "app.services.chat_attachment_service.ChatAttachmentService",
        lambda _session: service_instance,
    )

    tool = FileGenerateTool()
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
    )

    result = await tool.v1_0_0(
        ctx,
        {
            "filename": "report",
            "content": "Hello\n\nWorld",
            "format": "docx",
        },
    )

    assert result.success is True
    assert create_generated_attachment.await_args.kwargs["filename"] == "report.docx"
    generated_bytes = create_generated_attachment.await_args.kwargs["content"]
    assert generated_bytes[:2] == b"PK"
    session.commit.assert_awaited_once()
