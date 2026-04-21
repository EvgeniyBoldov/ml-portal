from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ConflictError
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance
from app.schemas.collections import CreateCollectionRequest
from app.services.collection_service import CollectionService, InvalidSchemaError


def test_create_request_requires_data_instance_id():
    with pytest.raises(ValidationError):
        CreateCollectionRequest(
            tenant_id=uuid4(),
            collection_type="table",
            slug="devices",
            name="Devices",
            fields=[],
        )


@pytest.mark.asyncio
async def test_create_rejects_non_data_instance_connector():
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalar_one_or_none=lambda: ToolInstance(
                id=uuid4(),
                slug="svc",
                name="Service connector",
                instance_kind="service",
                connector_type="mcp",
                connector_subtype=None,
                placement="remote",
                domain="mcp",
                url="https://example",
                config={},
                is_active=True,
            )
        )
    )

    service = CollectionService(session=session)
    service.get_by_slug = AsyncMock(return_value=None)

    with pytest.raises(InvalidSchemaError, match="not a data connector"):
        await service.create_collection(
            tenant_id=uuid4(),
            slug="devices",
            name="Devices",
            fields=[],
            collection_type="table",
            data_instance_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_update_rejects_data_instance_id_change_with_conflict():
    session = MagicMock()
    service = CollectionService(session=session)

    collection = Collection(
        id=uuid4(),
        tenant_id=uuid4(),
        collection_type="table",
        slug="devices",
        name="Devices",
        fields=[],
        status="ready",
        data_instance_id=uuid4(),
        is_active=True,
    )

    service.get_by_id = AsyncMock(return_value=collection)

    with pytest.raises(ConflictError, match="create a new collection instead"):
        await service.update_collection(
            collection_id=collection.id,
            data_instance_id=uuid4(),
        )
