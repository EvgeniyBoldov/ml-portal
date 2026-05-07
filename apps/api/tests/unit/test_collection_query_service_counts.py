from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.collection import CollectionType
from app.services.collection.query_service import CollectionQueryService


@pytest.mark.asyncio
async def test_effective_total_rows_for_table_uses_persisted_value():
    service = CollectionQueryService(session=AsyncMock(), host=SimpleNamespace())
    collection = SimpleNamespace(
        collection_type=CollectionType.TABLE.value,
        total_rows=42,
    )
    count = await service.get_effective_total_rows(collection)
    assert count == 42


@pytest.mark.asyncio
async def test_effective_total_rows_for_document_uses_memberships_count():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: 7))
    service = CollectionQueryService(session=session, host=SimpleNamespace())
    collection = SimpleNamespace(
        collection_type=CollectionType.DOCUMENT.value,
        tenant_id=uuid.uuid4(),
        id=uuid.uuid4(),
        total_rows=999,
    )
    count = await service.get_effective_total_rows(collection)
    assert count == 7
