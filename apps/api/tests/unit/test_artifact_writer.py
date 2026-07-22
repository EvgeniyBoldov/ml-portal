from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.artifact_writer import ArtifactWriter


@pytest.mark.asyncio
async def test_artifact_writer_returns_canonical_reference(monkeypatch) -> None:
    create = AsyncMock(
        return_value={
            "artifact_id": "11111111-1111-1111-1111-111111111111",
            "file_name": "report.txt",
            "content_type": "text/plain",
            "size_bytes": 6,
        }
    )
    monkeypatch.setattr(
        "app.services.artifact_writer.ChatAttachmentService",
        lambda _session: SimpleNamespace(create_generated_attachment=create),
    )

    artifact = await ArtifactWriter(SimpleNamespace()).write(
        chat_id="chat",
        owner_id="owner",
        filename="report.txt",
        content=b"report",
        content_type="text/plain",
    )

    assert artifact.artifact_id == "11111111-1111-1111-1111-111111111111"
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_artifact_writer_rejects_missing_chat() -> None:
    with pytest.raises(ValueError, match="chat context"):
        await ArtifactWriter(SimpleNamespace()).write(
            chat_id="",
            owner_id="owner",
            filename="report.txt",
            content=b"report",
            content_type="text/plain",
        )
