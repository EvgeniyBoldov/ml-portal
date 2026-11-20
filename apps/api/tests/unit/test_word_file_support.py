from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.file_generate import FileGenerateTool
from app.agents.context import ToolContext


def _make_docx_bytes(*paragraphs: str) -> bytes:
    pytest.importorskip("docx")
    from docx import Document  # type: ignore

    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


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
    generate = AsyncMock(
        return_value=SimpleNamespace(
            artifact_id=str(uuid4()),
            file_name="report.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=5,
        )
    )
    service_instance = SimpleNamespace(generate=generate)

    monkeypatch.setattr("app.core.db.get_session_factory", lambda: _SessionManager)
    monkeypatch.setattr(
        "app.services.file_generation_service.FileGenerationService",
        lambda _session: service_instance,
    )
    monkeypatch.setattr(
        "app.services.chat_artifact_reference_service.ChatArtifactReferenceService",
        lambda _session: SimpleNamespace(
            get_reference=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
            manifest=lambda _reference: {"artifact_id": "generated-artifact"},
        ),
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
    assert generate.await_args.kwargs["filename"] == "report"
    assert generate.await_args.kwargs["format_name"] == "docx"
    session.commit.assert_awaited_once()
