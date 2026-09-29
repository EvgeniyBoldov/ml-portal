from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.glossary_catalog_repository import GlossaryCatalogRepository, GlossaryTermRecord
from app.services.glossary_catalog_service import (
    GlossaryCatalogTerm,
    GlossaryCatalogService,
)

SOURCE_DOCUMENT_ID = uuid4()


class _Repository:
    async def list_visible(self):
        return [
            GlossaryTermRecord(
                canonical_term="evpn",
                aliases=("EVPN", "Ethernet VPN"),
                description="Ethernet Virtual Private Network",
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                source_document_id=SOURCE_DOCUMENT_ID,
                source_document_title="Словарь компании",
                source_section_ids=("section-1",),
            )
        ]


@pytest.mark.asyncio
async def test_glossary_catalog_service_returns_safe_entry_projection() -> None:
    repository = _Repository()
    service = GlossaryCatalogService(session=object())  # type: ignore[arg-type]
    service._repository = repository  # type: ignore[assignment]
    entries = await service.list_entries()

    assert entries == [
        GlossaryCatalogTerm(
            canonical_term="evpn",
            aliases=("EVPN", "Ethernet VPN"),
            description="Ethernet Virtual Private Network",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source_document_id=SOURCE_DOCUMENT_ID,
            source_document_title="Словарь компании",
            source_section_ids=("section-1",),
        )
    ]


@pytest.mark.asyncio
async def test_glossary_catalog_reads_canonical_defined_terms() -> None:
    term = SimpleNamespace(canonical_term="ПЗЭ", aliases=["поле золотых единорогов"],
                           definition="Поле золотых единорогов", updated_at=datetime.now(timezone.utc))
    candidate = SimpleNamespace(evidence_section_ids=["section-1"])
    snapshot = SimpleNamespace(document_id=uuid4())
    document = SimpleNamespace(title="Словарь компании")
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(term, candidate, snapshot, document)])))

    result = await GlossaryCatalogRepository(session).list_visible()

    assert len(result) == 1
    assert result[0].description == term.definition
    assert result[0].source_document_id == snapshot.document_id
    query = str(session.execute.call_args.args[0])
    assert "glossary_terms" in query
    assert "glossary_terms.is_active" in query
    assert "btrim(glossary_terms.definition)" in query
