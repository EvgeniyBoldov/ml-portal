from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.services.permission_service import EffectivePermissions
from app.api.v1.routers.collections import crud as collections_crud


def _fake_collection(slug: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        collection_type="table",
        slug=slug,
        name=slug,
        description=None,
        fields=[],
        total_rows=0,
        is_active=True,
        has_vector_search=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_collections_filters_denied_by_rbac(monkeypatch):
    allowed = _fake_collection("allowed")
    denied = _fake_collection("denied")
    fake_service = SimpleNamespace(
        list_collections=AsyncMock(return_value=[allowed, denied]),
        sync_collection_status=AsyncMock(return_value={"status": "ready", "details": {}}),
    )

    monkeypatch.setattr(
        collections_crud,
        "CollectionService",
        lambda _session: fake_service,
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_collection_permissions",
        AsyncMock(
            return_value=EffectivePermissions(
                collection_permissions={"allowed": True, "denied": False},
                default_collection_allow=False,
            )
        ),
    )

    response = await collections_crud.list_collections(
        active_only=True,
        tenant_id=None,
        session=AsyncMock(),
        user=SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="reader"),
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].slug == "allowed"


@pytest.mark.asyncio
async def test_get_collection_returns_404_when_denied_by_rbac(monkeypatch):
    denied = _fake_collection("denied")
    fake_service = SimpleNamespace(
        get_by_slug=AsyncMock(return_value=denied),
    )

    monkeypatch.setattr(
        collections_crud,
        "CollectionService",
        lambda _session: fake_service,
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_requested_tenant_id",
        AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        collections_crud,
        "_resolve_collection_permissions",
        AsyncMock(
            return_value=EffectivePermissions(
                collection_permissions={"denied": False},
                default_collection_allow=False,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await collections_crud.get_collection(
            slug="denied",
            tenant_id=None,
            session=AsyncMock(),
            user=SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="reader"),
        )

    assert exc.value.status_code == 404
