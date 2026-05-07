from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.routers.files import download_file_by_id
from app.services.file_delivery_service import ResolvedDownload


@pytest.mark.asyncio
async def test_download_file_by_id_returns_file_response(monkeypatch):
    resolved = ResolvedDownload(
        file_id="chatatt_11111111-1111-1111-1111-111111111111",
        bucket="chat-uploads",
        key="tenants/t/chats/c/a/file.txt",
        file_name="file.txt",
        content_type="text/plain",
        size_bytes=5,
    )

    resolve_mock = AsyncMock(return_value=resolved)
    get_object_mock = AsyncMock(return_value=b"hello")

    monkeypatch.setattr(
        "app.services.file_delivery_service.FileDeliveryService.resolve",
        resolve_mock,
    )
    monkeypatch.setattr(
        "app.api.v1.routers.files.s3_manager.get_object",
        get_object_mock,
    )

    response = await download_file_by_id(
        file_id=resolved.file_id,
        session=AsyncMock(),
        current_user=SimpleNamespace(id="11111111-1111-1111-1111-111111111111"),
        repo_factory=SimpleNamespace(tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    )

    assert response.status_code == 200
    assert response.body == b"hello"
    assert response.headers["content-disposition"] == 'attachment; filename="file.txt"'
