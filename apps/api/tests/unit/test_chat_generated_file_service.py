from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.chat_generated_file_service import ChatGeneratedFileService


@pytest.mark.asyncio
async def test_extracts_file_block_and_creates_attachment():
    attachment_service = AsyncMock()
    attachment_service.create_generated_attachment = AsyncMock(
        return_value={
            "id": "11111111-1111-1111-1111-111111111111",
            "file_id": "chatatt_11111111-1111-1111-1111-111111111111",
            "file_name": "report.txt",
            "file_ext": "txt",
            "content_type": "text/plain",
            "size_bytes": 12,
            "status": "generated",
        }
    )
    service = ChatGeneratedFileService(attachment_service)

    result = await service.extract_and_store(
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        chat_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        owner_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        assistant_text=(
            "Готово.\n\n"
            "```file name=report.txt\n"
            "hello world\n"
            "```\n"
        ),
    )

    assert "```file" not in result.cleaned_content
    assert len(result.attachments) == 1
    attachment_service.create_generated_attachment.assert_awaited_once()


@pytest.mark.asyncio
async def test_ignores_unsupported_file_extensions():
    attachment_service = AsyncMock()
    attachment_service.create_generated_attachment = AsyncMock()
    service = ChatGeneratedFileService(attachment_service)

    result = await service.extract_and_store(
        tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        chat_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        owner_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        assistant_text=(
            "```file name=payload.exe\n"
            "malicious\n"
            "```\n"
        ),
    )

    assert result.attachments == []
    attachment_service.create_generated_attachment.assert_not_awaited()
