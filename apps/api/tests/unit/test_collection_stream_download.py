from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.routers.collections import stream_download as download_router


@pytest.mark.asyncio
async def test_download_canonical_uses_membership_source_meta(monkeypatch):
    collection_id = uuid4()
    doc_uuid = uuid4()
    tenant_id = uuid4()
    s3_key = f"{tenant_id}/{doc_uuid}/canonical/file.txt"

    fake_collection = SimpleNamespace(id=collection_id, tenant_id=tenant_id)
    fake_document = SimpleNamespace(
        id=doc_uuid,
        tenant_id=tenant_id,
        s3_key_raw=None,
        s3_key_processed=None,
    )
    fake_membership = SimpleNamespace(
        source=SimpleNamespace(meta={"artifacts": {"canonical": {"key": s3_key}}})
    )

    monkeypatch.setattr(
        download_router,
        "_resolve_collection_and_doc_with_membership",
        AsyncMock(return_value=(fake_collection, fake_document, doc_uuid, MagicMock(), fake_membership)),
    )
    monkeypatch.setattr(
        download_router.s3_manager,
        "generate_presigned_url",
        AsyncMock(return_value="https://presigned"),
    )

    result = await download_router.download_collection_doc(
        collection_id=collection_id,
        doc_id=str(doc_uuid),
        kind="canonical",
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    assert result["url"] == "https://presigned"
    download_router.s3_manager.generate_presigned_url.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_canonical_not_found_when_no_source_and_no_s3_object(monkeypatch):
    collection_id = uuid4()
    doc_uuid = uuid4()
    tenant_id = uuid4()
    fake_collection = SimpleNamespace(id=collection_id, tenant_id=tenant_id)
    fake_document = SimpleNamespace(
        id=doc_uuid,
        tenant_id=tenant_id,
        s3_key_raw=None,
        s3_key_processed=None,
    )
    fake_membership = SimpleNamespace(source=None)

    session = AsyncMock()

    monkeypatch.setattr(
        download_router,
        "_resolve_collection_and_doc_with_membership",
        AsyncMock(return_value=(fake_collection, fake_document, doc_uuid, MagicMock(), fake_membership)),
    )
    monkeypatch.setattr(download_router.s3_manager, "list_objects", AsyncMock(return_value=[]))

    with pytest.raises(HTTPException) as exc:
        await download_router.download_collection_doc(
            collection_id=collection_id,
            doc_id=str(doc_uuid),
            kind="canonical",
            session=session,
            user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "File not found"
