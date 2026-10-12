from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.routers.admin.collections_shared import build_collection_response
from app.api.v1.routers.collections.crud import _build_collection_response


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_collection_response, _build_collection_response])
async def test_template_response_survives_changed_encoder_dimension(builder):
    async def align(_collection, *, ensure_vector_infra=True):
        if ensure_vector_infra:
            raise ValueError("Qdrant collection 'coll_template' has vector dim 384, expected 1024")

    service = SimpleNamespace(
        ensure_contract_fields_present=AsyncMock(side_effect=align),
        sync_collection_status=AsyncMock(return_value={"status": "ready", "details": {}}),
        get_effective_total_rows=AsyncMock(return_value=3),
    )
    collection = SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), collection_type="template", slug="template", name="Templates",
        fields=[], source_contract=None, current_version=None, table_name="template_rows", table_schema=None,
        has_vector_search=True, vector_config={}, qdrant_collection_name="coll_template",
        vectorized_rows=3, total_chunks=3, failed_rows=0, vectorization_progress=100.0,
        is_fully_vectorized=True, data_instance_id=uuid4(), data_instance=None, last_sync_at=None,
        is_active=True, current_version_id=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    response = await builder(service, collection)
    assert response.slug == "template"
    assert response.total_rows == 3
    service.ensure_contract_fields_present.assert_awaited_once_with(collection, ensure_vector_infra=False)
