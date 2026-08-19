from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.repositories.glossary_catalog_repository import GlossaryEntryRecord
from app.services.glossary_catalog_service import (
    GlossaryCatalogEntry,
    GlossaryCatalogService,
)


class _Repository:
    def __init__(self) -> None:
        self.user_id = None
        self.tenant_id = None

    async def list_visible(self, *, user_id, tenant_id):
        self.user_id = user_id
        self.tenant_id = tenant_id
        return [
            GlossaryEntryRecord(
                canonical_term="evpn",
                aliases=("EVPN", "Ethernet VPN"),
                description="Ethernet Virtual Private Network",
                entity_type="term",
                scope="tenant",
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]


@pytest.mark.asyncio
async def test_glossary_catalog_service_returns_safe_entry_projection() -> None:
    repository = _Repository()
    service = GlossaryCatalogService(session=object())  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    tenant_id = uuid4()

    user_id = uuid4()
    entries = await service.list_entries(user_id=user_id, tenant_id=tenant_id)

    assert repository.user_id == user_id
    assert repository.tenant_id == tenant_id
    assert entries == [
        GlossaryCatalogEntry(
            canonical_term="evpn",
            aliases=("EVPN", "Ethernet VPN"),
            description="Ethernet Virtual Private Network",
            entity_type="term",
            scope="tenant",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
